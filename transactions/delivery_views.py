"""
Delivery fee calculation API endpoints
"""
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .delivery_service import DeliveryFeeCalculator
import json


@method_decorator(csrf_exempt, name='dispatch')
class CalculateDeliveryFeeView(View):
    """API endpoint to calculate delivery fee for a single address"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            # Validate required fields
            required_fields = ['restaurant_lat', 'restaurant_lng', 'customer_lat', 'customer_lng']
            if not all(field in data for field in required_fields):
                return JsonResponse({
                    'error': 'Missing required fields',
                    'required': required_fields
                }, status=400)
            
            # Calculate fee
            calculator = DeliveryFeeCalculator()
            result = calculator.calculate_fee(
                origin_lat=float(data['restaurant_lat']),
                origin_lng=float(data['restaurant_lng']),
                dest_lat=float(data['customer_lat']),
                dest_lng=float(data['customer_lng'])
            )
            
            if result['success']:
                return JsonResponse(result)
            else:
                return JsonResponse(result, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': f'Invalid coordinate values: {str(e)}'}, status=400)
        except Exception as e:
            return JsonResponse({'error': 'Internal server error'}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class CalculateMultipleFeesView(View):
    """Calculate fees for multiple delivery addresses"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            if 'restaurant_lat' not in data or 'restaurant_lng' not in data:
                return JsonResponse({'error': 'Missing restaurant coordinates'}, status=400)
            
            if 'destinations' not in data or not isinstance(data['destinations'], list):
                return JsonResponse({'error': 'Missing or invalid destinations list'}, status=400)
            
            if len(data['destinations']) > 100:
                return JsonResponse({'error': 'Maximum 100 destinations allowed'}, status=400)
            
            # Convert destinations to tuples
            destinations = [
                (float(dest['lat']), float(dest['lng'])) 
                for dest in data['destinations']
            ]
            
            calculator = DeliveryFeeCalculator()
            results = calculator.calculate_multiple_fees(
                origin_lat=float(data['restaurant_lat']),
                origin_lng=float(data['restaurant_lng']),
                destinations=destinations
            )
            
            return JsonResponse({
                'success': True,
                'results': results
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': f'Invalid coordinate values: {str(e)}'}, status=400)
        except Exception as e:
            return JsonResponse({'error': 'Internal server error'}, status=500)
