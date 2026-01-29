"""
Celery tasks for asynchronous delivery fee calculation
Place this in transactions/tasks.py or create a separate delivery_tasks.py

This allows long-running distance calculations to happen in the background
"""

from celery import shared_task
from django.core.cache import cache
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def calculate_delivery_fee_async(self, order_id, origin_lat, origin_lng, dest_lat, dest_lng):
    """
    Asynchronously calculate delivery fee for an order
    
    Args:
        order_id: Order ID to update
        origin_lat: Restaurant latitude
        origin_lng: Restaurant longitude
        dest_lat: Customer latitude
        dest_lng: Customer longitude
    
    Returns:
        Dictionary with calculation result
    """
    from .models import Order
    from .delivery_service import DeliveryFeeCalculator
    
    try:
        order = Order.objects.get(id=order_id)
        calculator = DeliveryFeeCalculator()
        
        result = calculator.calculate_fee(
            origin_lat, origin_lng,
            dest_lat, dest_lng
        )
        
        if result['success']:
            # Update order with delivery fee
            order.delivery_fee = Decimal(str(result['fee']))
            order.delivery_distance = result['distance']
            order.delivery_duration = result['duration']
            order.delivery_distance_miles = result['distance_miles']
            order.save()
            
            logger.info(f"Delivery fee calculated for order {order_id}: ${result['fee']}")
            return {
                'success': True,
                'order_id': order_id,
                'fee': result['fee'],
                'distance': result['distance']
            }
        else:
            logger.warning(f"Failed to calculate delivery fee for order {order_id}: {result['error']}")
            return {
                'success': False,
                'order_id': order_id,
                'error': result['error']
            }
            
    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
        return {'success': False, 'error': f'Order {order_id} not found'}
    except Exception as exc:
        logger.error(f"Error calculating delivery fee: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def calculate_multiple_delivery_fees_async(self, origin_lat, origin_lng, destinations):
    """
    Asynchronously calculate delivery fees for multiple destinations
    
    Args:
        origin_lat: Restaurant latitude
        origin_lng: Restaurant longitude
        destinations: List of dicts with 'lat', 'lng', and optionally 'order_id'
    
    Returns:
        List of calculation results with order IDs
    """
    from .models import Order
    from .delivery_service import DeliveryFeeCalculator
    
    try:
        calculator = DeliveryFeeCalculator()
        
        # Convert to tuples for calculator
        dest_tuples = [(d['lat'], d['lng']) for d in destinations]
        
        results = calculator.calculate_multiple_fees(
            origin_lat, origin_lng,
            dest_tuples
        )
        
        # Update orders if order_ids provided
        for idx, result in enumerate(results):
            if idx < len(destinations) and 'order_id' in destinations[idx]:
                order_id = destinations[idx]['order_id']
                try:
                    order = Order.objects.get(id=order_id)
                    if result['success']:
                        order.delivery_fee = Decimal(str(result['fee']))
                        order.delivery_distance = result['distance']
                        order.delivery_duration = result['duration']
                        order.delivery_distance_miles = result['distance_miles']
                        order.save()
                        logger.info(f"Batch: Updated delivery fee for order {order_id}")
                except Order.DoesNotExist:
                    logger.warning(f"Order {order_id} not found in batch update")
        
        logger.info(f"Batch delivery fee calculation completed: {len(results)} destinations")
        return {
            'success': True,
            'processed': len(results),
            'results': results
        }
        
    except Exception as exc:
        logger.error(f"Error in batch delivery calculation: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def cache_delivery_fees_for_restaurant(restaurant_id):
    """
    Pre-calculate and cache delivery fees for a restaurant's service area
    Useful for improving UX when customers check delivery availability
    
    Args:
        restaurant_id: Restaurant ID
    """
    from .models import Order
    from .delivery_service import DeliveryFeeCalculator
    from store.models import Restaurant  # Adjust import based on your models
    
    try:
        restaurant = Restaurant.objects.get(id=restaurant_id)
        calculator = DeliveryFeeCalculator()
        
        # Get recent orders to sample common delivery areas
        recent_orders = Order.objects.filter(
            restaurant_id=restaurant_id
        ).order_by('-created_at')[:50]
        
        cached_count = 0
        for order in recent_orders:
            if all([order.restaurant_lat, order.restaurant_lng, 
                   order.customer_lat, order.customer_lng]):
                result = calculator.calculate_fee(
                    order.restaurant_lat,
                    order.restaurant_lng,
                    order.customer_lat,
                    order.customer_lng
                )
                cached_count += 1
        
        logger.info(f"Cached {cached_count} delivery fee calculations for restaurant {restaurant_id}")
        return {'success': True, 'cached': cached_count}
        
    except Exception as exc:
        logger.error(f"Error caching delivery fees: {exc}")
        return {'success': False, 'error': str(exc)}


# ========================
# Using These Tasks in Views
# ========================

"""
Example: Using async task in your view

from .tasks import calculate_delivery_fee_async

def create_order(request):
    from rest_framework.response import Response
    
    data = request.data
    
    # Create order without delivery fee first
    order = Order.objects.create(
        user=request.user,
        restaurant_lat=data['restaurant_lat'],
        restaurant_lng=data['restaurant_lng'],
        customer_lat=data['customer_lat'],
        customer_lng=data['customer_lng'],
        # ... other fields
    )
    
    # Calculate delivery fee asynchronously
    calculate_delivery_fee_async.delay(
        order.id,
        float(data['restaurant_lat']),
        float(data['restaurant_lng']),
        float(data['customer_lat']),
        float(data['customer_lng'])
    )
    
    # Return order immediately (delivery fee will be updated in background)
    return Response(OrderSerializer(order).data, status=201)


# Example: Using async for multiple orders

from .tasks import calculate_multiple_delivery_fees_async

def bulk_calculate_delivery_fees(request):
    from rest_framework.response import Response
    
    data = request.data
    destinations = [
        {
            'lat': d['lat'],
            'lng': d['lng'],
            'order_id': d['order_id']  # Optional: will auto-update these orders
        }
        for d in data['destinations']
    ]
    
    # Start async calculation
    task = calculate_multiple_delivery_fees_async.delay(
        float(data['restaurant_lat']),
        float(data['restaurant_lng']),
        destinations
    )
    
    return Response({
        'message': 'Delivery fees being calculated',
        'task_id': task.id
    }, status=202)


# Example: Check task status

from celery.result import AsyncResult

def get_task_status(request, task_id):
    from rest_framework.response import Response
    
    result = AsyncResult(task_id)
    
    return Response({
        'task_id': task_id,
        'status': result.status,
        'result': result.result
    })
"""
