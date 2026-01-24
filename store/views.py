from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import PermissionDenied
from .models import Product, Category
from authentication.core.base_view import BaseAPIView
from .serializers import ProductSerializer, CategorySerializer
from authentication.core.response import standardized_response
from rest_framework.response import Response
from rest_framework import generics
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import FilterSet, NumberFilter, CharFilter
from rest_framework.filters import OrderingFilter, SearchFilter
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse
from django.utils import timezone

from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Product, Cart, CartItem, Favourite, Review, Category
from .serializers import (
    ProductSerializer, CreateProductSerializer, CartSerializer, CartItemSerializer,
    FavouriteSerializer, ReviewSerializer, ProductApprovalSerializer, PendingProductsSerializer,
    CategorySerializer, VendorAdminProductDetailSerializer
)

from rest_framework import serializers
from authentication.core.base_view import BaseAPIView
from authentication.core.response import standardized_response
from authentication.core.permissions import IsAdminOrVendor, IsAdmin, IsVendor

# ---------------------------
# Products FilterSet
# ---------------------------
class ProductFilterSet(FilterSet):
    price = NumberFilter(field_name='price', lookup_expr='exact', label='Exact Price')
    min_price = NumberFilter(field_name='price', lookup_expr='gte', label='Minimum Price')
    max_price = NumberFilter(field_name='price', lookup_expr='lte', label='Maximum Price')
    store = CharFilter(field_name='store__id', lookup_expr='exact')
    
    class Meta:
        model = Product
        fields = ['store', 'category']


# ---------------------------
# Products List & Filtering
# ---------------------------
class ProductListView(BaseAPIView, generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilterSet
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'name']

    def get_queryset(self):
        """Only show approved products that have been submitted"""
        return Product.objects.filter(
            approval_status='approved',
            publish_status='submitted'
        ).all()

    @extend_schema(
        parameters=[
            OpenApiParameter(name='store', description='Filter by store/vendor ID', required=False, type=int),
            OpenApiParameter(name='price', description='Filter by exact price', required=False, type=float),
            OpenApiParameter(name='min_price', description='Filter by minimum price', required=False, type=float),
            OpenApiParameter(name='max_price', description='Filter by maximum price', required=False, type=float),
            OpenApiParameter(name='category', description='Filter by category', required=False, type=str),
            OpenApiParameter(name='search', description='Search by name or description', required=False, type=str),
            OpenApiParameter(name='ordering', description='Order by price or name', required=False, type=str),
        ],
        responses={200: ProductSerializer(many=True)},
        description="Retrieve a list of products. Supports filtering by exact price or price range, search, and ordering. Only shows approved products."
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(standardized_response(data=serializer.data))
        serializer = self.get_serializer(queryset, many=True)
        return Response(standardized_response(data=serializer.data))


class ProductDetailView(BaseAPIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[OpenApiParameter(name='slug', description='Product slug', required=True, type=str)],
        responses={200: ProductSerializer, 404: {"description": "Product not found"}},
        description="Retrieve details of a specific product by slug"
    )
    def get(self, request, slug):
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response(
                standardized_response(success=False, error="Product not found"),
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ProductSerializer(product)
        return Response(standardized_response(data=serializer.data))



@extend_schema(
    tags=["Products"],
    description="Create a new product as draft with multiple images and optional video. At least one image is required and must be marked as main.",
    request=CreateProductSerializer,
    examples=[
        OpenApiExample(
            "Create product with images",
            summary="Add new product with images",
            value={
                "name": "Wireless Headphones",
                "description": "High-quality wireless headphones with noise cancellation",
                "category": "electronics",
                "brand": "AudioBrand",
                "price": 150.00,
                "discounted_price": 120.00,
                "stock": 50,
                "tags": "headphones, wireless, audio",
                "variants": {
                    "colors": ["black", "white", "silver"],
                    "sizes": ["M", "L"]
                },
                "images_data": [
                    {
                        "is_main": True,
                        "alt_text": "Main product image",
                        "variant_association": None
                    },
                    {
                        "is_main": False,
                        "alt_text": "Black variant",
                        "variant_association": {"colors": ["black"]}
                    }
                ],
                "video_data": {
                    "title": "Product Demo",
                    "description": "See the product in action"
                }
            }
        )
    ],
    responses={201: CreateProductSerializer, 400: {"description": "Invalid input"}}
)
class CreateProductView(BaseAPIView, generics.CreateAPIView):
    permission_classes = [IsAuthenticated, IsAdminOrVendor]
    serializer_class = CreateProductSerializer

    def perform_create(self, serializer):
        # Extract vendor from authenticated user
        from users.services.profile_resolver import ProfileResolver
        vendor = ProfileResolver.resolve_vendor(self.request.user)

        # Check if vendor exists
        if vendor is None:
            raise serializers.ValidationError({
                "detail": "You are not registered as a vendor."
            })

        # Check vendor verification status
        if not vendor.is_verified_vendor:
            raise serializers.ValidationError({
                "detail": "Your vendor account is not verified. Please complete verification before adding products."
            })

        # Save the product as draft
        product = serializer.save(store=vendor, publish_status='draft')
        
        # Handle images
        images_data = self.request.data.get('images_data', [])
        self._create_product_images(product, images_data, serializer.validated_data.get('variants'))
        
        # Handle video
        video_data = self.request.data.get('video_data')
        if video_data:
            self._create_product_video(product, video_data)

    def _create_product_images(self, product, images_data, variants):
        """Helper function to create product images with variant associations"""
        from .models import ProductImage, validate_variant_association
        
        for idx, img_data in enumerate(images_data):
            is_main = img_data.get('is_main', False)
            image_file = img_data.get('image')
            alt_text = img_data.get('alt_text')
            variant_assoc = img_data.get('variant_association')
            
            # Validate variant association if provided
            if variant_assoc and variants:
                is_valid, error_msg = validate_variant_association(variant_assoc, variants)
                if not is_valid:
                    raise serializers.ValidationError({
                        "images_data": f"Image {idx + 1}: {error_msg}"
                    })
            
            # Create the image
            ProductImage.objects.create(
                product=product,
                image=image_file,
                is_main=is_main,
                alt_text=alt_text,
                variant_association=variant_assoc,
                display_order=idx
            )

    def _create_product_video(self, product, video_data):
        """Helper function to create product video with size validation"""
        from .models import ProductVideo, validate_video_size
        
        video_file = video_data.get('video')
        
        # Validate video size
        if hasattr(video_file, 'size'):
            is_valid, error_msg = validate_video_size(video_file.size)
            if not is_valid:
                raise serializers.ValidationError({
                    "video_data": error_msg
                })
        
        ProductVideo.objects.create(
            product=product,
            video=video_file,
            title=video_data.get('title'),
            description=video_data.get('description')
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Return the complete product with images and videos
        product = Product.objects.get(pk=serializer.instance.pk)
        response_serializer = self.get_serializer(product)
        
        headers = self.get_success_headers(response_serializer.data)
        return Response(
            standardized_response(data=response_serializer.data, message="Product created successfully as draft with media"),
            status=status.HTTP_201_CREATED,
            headers=headers
        )



@extend_schema(
    tags=["Products"],
    description="Update specific fields of a product (authenticated vendor or admin only). Patchable fields: price, stock, description, category, image.",
    parameters=[OpenApiParameter(name='slug', description='Product slug', required=True, type=str)],
    request=ProductSerializer,
    examples=[
        OpenApiExample(
            "Patch product example",
            summary="Update product stock",
            value={"stock": 10}
        )
    ],
    responses={
        200: ProductSerializer,
        404: {"description": "Product not found"},
        403: {"description": "Permission denied"}
    }
)
class PatchProductView(BaseAPIView, generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductSerializer
    lookup_field = 'slug'

    def get_object(self):
        slug = self.kwargs.get('slug')
        product = get_object_or_404(Product, slug=slug)

        # Permission check
        user = self.request.user
        if user.is_admin:
            return product
        elif user.is_vendor:
            if hasattr(user, 'vendor_profile') and product.store == user.vendor_profile:
                return product
            else:
                raise PermissionError("You cannot update a product you do not own.")
        else:
            raise PermissionError("You do not have permission to update this product.")

    def patch(self, request, *args, **kwargs):
        product = self.get_object()

        # Only allow patching specific fields
        allowed_fields = ['price', 'discounted_price', 'stock', 'description', 'category', 'brand', 'tags', 'variants', 'image']
        data = {k: v for k, v in request.data.items() if k in allowed_fields}

        serializer = self.get_serializer(product, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(standardized_response(data=serializer.data, message="Product updated successfully"))




@extend_schema(
    tags=["store"],
    summary="Delete a product",
    description="Deletes a product. Only vendor-owner or admin can delete. Returns serialized result.",
    responses={
        200: OpenApiResponse(description="Product deleted successfully."),
        403: OpenApiResponse(description="Not allowed to delete this product."),
        404: OpenApiResponse(description="Product not found"),
    },
)
class ProductDeleteView(generics.DestroyAPIView):
    queryset = Product.objects.all()
    lookup_field = "slug"
    permission_classes = [IsAuthenticated, IsAdminOrVendor]

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()

        # Serialize before deletion
        serialized = ProductSerializer(instance).data

        # Perform vendor/admin validation + deletion
        response = self.perform_destroy(instance)

        # If perform_destroy returned an error Response, return it directly
        if isinstance(response, Response):
            return response

        # Successful deletion
        return Response(
            {
                "status": "success",
                "message": "Product deleted successfully.",
                "data": serialized,
            },
            status=status.HTTP_200_OK
        )

    def perform_destroy(self, instance):
        user = self.request.user

        # Admin can delete anything
        if user.is_staff or user.is_superuser:
            instance.delete()
            return

        # Vendor must own the product — return serialized error response
        if instance.vendor != user:
            return Response(
                {
                    "status": "error",
                    "message": "You are not allowed to delete this product.",
                    "data": None,
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # Vendor-owner can delete
        instance.delete()


# ======================================================
# CART VIEWS
# ======================================================
@extend_schema(
    tags=["Cart"],
    description="Retrieve the authenticated user's shopping cart, including all cart items and total price.",
    responses={200: CartSerializer}
)
class CartView(BaseAPIView, generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    def get(self, request, *args, **kwargs):
        cart, created = Cart.objects.get_or_create(customer=request.user)
        serializer = self.get_serializer(cart)
        return Response(standardized_response(data=serializer.data))


@extend_schema(
    tags=["Cart"],
    description="Add a product to the authenticated user's cart or update its quantity if already present.",
    request=CartItemSerializer,
    examples=[
        OpenApiExample(
            "Add item example",
            summary="Add item to cart",
            value={"product_id": 3, "quantity": 2}
        )
    ],
    responses={
        201: CartItemSerializer,
        400: {"description": "Invalid data or product not found"}
    },
)
class AddToCartView(BaseAPIView, generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartItemSerializer

    def post(self, request):
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))
        product = get_object_or_404(Product, id=product_id)

        cart, _ = Cart.objects.get_or_create(customer=request.user)
        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)

        if not created:
            cart_item.quantity += quantity
        else:
            cart_item.quantity = quantity

        cart_item.save()
        serializer = self.get_serializer(cart_item)
        return Response(standardized_response(data=serializer.data, message="Item added to cart"))


@extend_schema(
    tags=["Cart"],
    description="Remove a specific product from the authenticated user's cart.",
    parameters=[OpenApiParameter(name='slug', description='Product slug', required=True, type=str)],
    responses={
        200: {"description": "Item removed successfully"},
        404: {"description": "Item not found in cart"}
    },
)
class RemoveFromCartView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, slug):
        cart = get_object_or_404(Cart, customer=request.user)
        product = get_object_or_404(Product, slug=slug)
        item = get_object_or_404(CartItem, cart=cart, product=product)
        item.delete()
        return Response(standardized_response(message="Item removed from cart"))


# ======================================================
# FAVOURITES VIEWS
# ======================================================
@extend_schema(
    tags=["Favourites"],
    description="Retrieve all products favourited by the authenticated user.",
    responses={200: FavouriteSerializer(many=True)},
)
class FavouriteListView(BaseAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FavouriteSerializer

    def get_queryset(self):
        return Favourite.objects.filter(customer=self.request.user)


@extend_schema(
    tags=["Favourites"],
    description="Add a product to the authenticated user's favourites list.",
    request=FavouriteSerializer,
    examples=[
        OpenApiExample(
            "Add favourite example",
            summary="Add to favourites",
            value={"product_id": 5}
        )
    ],
    responses={
        201: FavouriteSerializer,
        400: {"description": "Already in favourites"}
    }
)
class AddFavouriteView(BaseAPIView, generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FavouriteSerializer

    def post(self, request):
        product_id = request.data.get('product_id')
        product = get_object_or_404(Product, id=product_id)

        fav, created = Favourite.objects.get_or_create(customer=request.user, product=product)
        if not created:
            return Response(standardized_response(success=False, error="Already in favourites"), status=400)

        serializer = self.get_serializer(fav)
        return Response(standardized_response(data=serializer.data, message="Added to favourites"))


@extend_schema(
    tags=["Favourites"],
    description="Remove a specific product from the authenticated user's favourites list.",
    parameters=[OpenApiParameter(name='slug', description='Product slug', required=True, type=str)],
    responses={
        200: {"description": "Removed successfully"},
        404: {"description": "Product not in favourites"}
    }
)
class RemoveFavouriteView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        fav = Favourite.objects.filter(customer=request.user, product=product).first()
        if fav:
            fav.delete()
            return Response(standardized_response(message="Removed from favourites"))
        return Response(standardized_response(success=False, error="Not in favourites"), status=404)


# ======================================================
# REVIEW VIEWS
# ======================================================
@extend_schema(
    tags=["Reviews"],
    description="Retrieve all reviews for a specific product using its slug.",
    parameters=[
        OpenApiParameter(name='slug', description='Product slug', required=True, type=str)
    ],
    responses={200: ReviewSerializer(many=True)}
)
class ProductReviewListView(BaseAPIView, generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ReviewSerializer

    def get_queryset(self):
        product_slug = self.kwargs.get('slug')
        product = get_object_or_404(Product, slug=product_slug)
        return Review.objects.filter(product=product)


@extend_schema(
    tags=["Reviews"],
    description="Add or update a review for a specific product (authenticated users only).",
    parameters=[
        OpenApiParameter(name='slug', description='Product slug', required=True, type=str)
    ],
    request=ReviewSerializer,
    examples=[
        OpenApiExample(
            "Add review example",
            summary="Post a review",
            value={"rating": 5, "comment": "Great product!"}
        )
    ],
    responses={
        201: ReviewSerializer,
        400: {"description": "Invalid input"}
    }
)
class AddReviewView(BaseAPIView, generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ReviewSerializer

    def post(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        rating = request.data.get('rating')
        comment = request.data.get('comment', '')

        review, created = Review.objects.update_or_create(
            product=product,
            customer=request.user,
            defaults={'rating': rating, 'comment': comment}
        )

        serializer = self.get_serializer(review)
        return Response(standardized_response(data=serializer.data, message="Review added successfully"))


# ---------------------------
# Admin Product Approval
# ---------------------------
@extend_schema(
    tags=["Admin - Product Approval"],
    description="Get list of all pending products awaiting approval (Admin only). Supports filtering and pagination.",
    parameters=[
        OpenApiParameter(name='status', description='Filter by approval status (pending, approved, rejected)', required=False, type=str),
        OpenApiParameter(name='store', description='Filter by store/vendor ID', required=False, type=int),
        OpenApiParameter(name='category', description='Filter by category', required=False, type=str),
        OpenApiParameter(name='ordering', description='Order results', required=False, type=str),
    ],
    responses={200: PendingProductsSerializer(many=True)},
)
class PendingProductsListView(BaseAPIView, generics.ListAPIView):
    """
    Admin endpoint to list all pending products requiring approval.
    Only accessible by admin users.
    """
    permission_classes = [IsAdmin]
    serializer_class = PendingProductsSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ['approval_status', 'store', 'category']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name', 'price']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get all products with optional filtering by approval status"""
        return Product.objects.all().select_related('store', 'approved_by')

    @extend_schema(
        responses={200: PendingProductsSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                standardized_response(
                    data=serializer.data,
                    message=f"Found {queryset.count()} products"
                )
            )
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            standardized_response(
                data=serializer.data,
                message=f"Found {queryset.count()} products"
            )
        )


@extend_schema(
    tags=["Admin - Product Approval"],
    description="Approve a product and make it visible to customers (Admin only).",
    parameters=[
        OpenApiParameter(name='slug', description='Product slug', required=True, type=str)
    ],
    request=ProductApprovalSerializer,
    responses={
        200: {"description": "Product approved successfully"},
        404: {"description": "Product not found"},
        403: {"description": "Only admin can approve products"}
    }
)
class ApproveProductView(BaseAPIView):
    """
    Admin endpoint to approve a pending product.
    Marks the product as approved and makes it visible to all customers.
    """
    permission_classes = [IsAdmin]

    def post(self, request, slug):
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response(
                standardized_response(success=False, error="Product not found"),
                status=status.HTTP_404_NOT_FOUND
            )

        # Update product approval status
        product.approval_status = 'approved'
        product.approved_by = request.user
        product.approval_date = timezone.now()
        product.rejection_reason = None
        product.save()

        # Send email notification to vendor
        from store.tasks import send_product_approval_email_task
        send_product_approval_email_task.delay(product.id)

        serializer = PendingProductsSerializer(product)
        return Response(
            standardized_response(
                data=serializer.data,
                message=f"Product '{product.name}' approved successfully"
            ),
            status=status.HTTP_200_OK
        )


@extend_schema(
    tags=["Admin - Product Approval"],
    description="Reject a product with a rejection reason (Admin only).",
    parameters=[
        OpenApiParameter(name='slug', description='Product slug', required=True, type=str)
    ],
    request=ProductApprovalSerializer,
    responses={
        200: {"description": "Product rejected successfully"},
        404: {"description": "Product not found"},
        403: {"description": "Only admin can reject products"}
    }
)
class RejectProductView(BaseAPIView):
    """
    Admin endpoint to reject a pending product.
    Stores rejection reason for vendor feedback.
    """
    permission_classes = [IsAdmin]

    def post(self, request, slug):
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response(
                standardized_response(success=False, error="Product not found"),
                status=status.HTTP_404_NOT_FOUND
            )

        reason = request.data.get('rejection_reason', 'No reason provided')
        if not reason or not reason.strip():
            return Response(
                standardized_response(success=False, error="Rejection reason is required"),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update product rejection status
        product.approval_status = 'rejected'
        product.approved_by = request.user
        product.approval_date = timezone.now()
        product.rejection_reason = reason
        product.save()

        # Send email notification to vendor
        from store.tasks import send_product_rejection_email_task
        send_product_rejection_email_task.delay(product.id, reason)

        serializer = PendingProductsSerializer(product)
        return Response(
            standardized_response(
                data=serializer.data,
                message=f"Product '{product.name}' rejected successfully"
            ),
            status=status.HTTP_200_OK
        )


@extend_schema(
    tags=["Admin - Product Approval"],
    description="Get approval statistics - count of products by approval status (Admin only).",
    responses={
        200: {
            "description": "Approval statistics",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "pending": 5,
                            "approved": 20,
                            "rejected": 2,
                            "total": 27
                        }
                    }
                }
            }
        }
    }
)
class ApprovalStatsView(BaseAPIView):
    """
    Get approval statistics showing count of products by status.
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        stats = {
            'pending': Product.objects.filter(approval_status='pending').count(),
            'approved': Product.objects.filter(approval_status='approved').count(),
            'rejected': Product.objects.filter(approval_status='rejected').count(),
        }
        stats['total'] = sum(stats.values())

        return Response(
            standardized_response(
                data=stats,
                message="Approval statistics retrieved successfully"
            )
        )


# ---------------------------
# Draft Product Management
# ---------------------------
@extend_schema(
    tags=["Products - Drafts"],
    description="Get list of draft products for the authenticated vendor (vendor only)",
    parameters=[
        OpenApiParameter(name='ordering', description='Order by: created_at, name, price', required=False, type=str),
    ],
    responses={200: ProductSerializer(many=True)},
)
class VendorDraftProductsView(BaseAPIView, generics.ListAPIView):
    """
    List all draft products created by the authenticated vendor.
    Only vendors can access this endpoint.
    """
    permission_classes = [IsAuthenticated, IsVendor]
    serializer_class = ProductSerializer
    filter_backends = [OrderingFilter, SearchFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name', 'price']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get only draft products for the current vendor"""
        from users.services.profile_resolver import ProfileResolver
        vendor = ProfileResolver.resolve_vendor(self.request.user)
        
        if vendor is None:
            return Product.objects.none()
        
        return Product.objects.filter(
            store=vendor,
            publish_status='draft'
        ).select_related('store', 'approved_by')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                standardized_response(
                    data=serializer.data,
                    message=f"Found {queryset.count()} draft products"
                )
            )
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            standardized_response(
                data=serializer.data,
                message=f"Found {queryset.count()} draft products"
            )
        )


@extend_schema(
    tags=["Products - Drafts"],
    description="Submit/publish a draft product for admin approval (vendor only)",
    parameters=[
        OpenApiParameter(name='slug', description='Product slug', required=True, type=str)
    ],
    responses={
        200: {"description": "Product submitted successfully"},
        404: {"description": "Product not found"},
        403: {"description": "Permission denied or product not a draft"}
    }
)
class SubmitDraftProductView(BaseAPIView):
    """
    Submit a draft product for admin approval.
    Changes publish_status from 'draft' to 'submitted'.
    Only the vendor who created the product can submit it.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def post(self, request, slug):
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response(
                standardized_response(success=False, error="Product not found"),
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if user is the vendor who owns this product
        from users.services.profile_resolver import ProfileResolver
        vendor = ProfileResolver.resolve_vendor(request.user)
        
        if vendor is None or product.store != vendor:
            return Response(
                standardized_response(success=False, error="You don't have permission to submit this product"),
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if product is in draft status
        if product.publish_status != 'draft':
            return Response(
                standardized_response(
                    success=False, 
                    error=f"Only draft products can be submitted. This product is {product.publish_status}"
                ),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate that all required fields are filled
        required_fields = ['name', 'description', 'category', 'price', 'stock']
        missing_fields = []
        
        for field in required_fields:
            value = getattr(product, field)
            if value is None or value == '':
                missing_fields.append(field)
        
        if missing_fields:
            return Response(
                standardized_response(
                    success=False,
                    error=f"Cannot submit product. Missing required fields: {', '.join(missing_fields)}"
                ),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Submit the product
        product.publish_status = 'submitted'
        product.approval_status = 'pending'  # Reset to pending if it was rejected before
        product.save()

        serializer = ProductSerializer(product)
        return Response(
            standardized_response(
                data=serializer.data,
                message="Product submitted successfully for admin approval"
            ),
            status=status.HTTP_200_OK
        )


@extend_schema(
    tags=["Products - Drafts"],
    description="Update a draft product (vendor only). Can modify any field while in draft status.",
    parameters=[
        OpenApiParameter(name='slug', description='Product slug', required=True, type=str)
    ],
    request=ProductSerializer,
    responses={
        200: ProductSerializer,
        404: {"description": "Product not found"},
        403: {"description": "Permission denied or product not a draft"}
    }
)
class UpdateDraftProductView(BaseAPIView):
    """
    Update a draft product's details.
    Only available for products in draft status.
    Only the vendor who created the product can update it.
    """
    permission_classes = [IsAuthenticated, IsVendor]
    serializer_class = ProductSerializer

    def patch(self, request, slug):
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response(
                standardized_response(success=False, error="Product not found"),
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if user is the vendor who owns this product
        from users.services.profile_resolver import ProfileResolver
        vendor = ProfileResolver.resolve_vendor(request.user)
        
        if vendor is None or product.store != vendor:
            return Response(
                standardized_response(success=False, error="You don't have permission to update this product"),
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if product is in draft status
        if product.publish_status != 'draft':
            return Response(
                standardized_response(
                    success=False,
                    error=f"Only draft products can be updated. This product is {product.publish_status}"
                ),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update the product with provided fields
        serializer = self.serializer_class(product, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response(
                standardized_response(
                    data=serializer.data,
                    message="Draft product updated successfully"
                ),
                status=status.HTTP_200_OK
            )
        
        return Response(
            standardized_response(success=False, error=serializer.errors),
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    tags=["Products - Drafts"],
    description="Delete a draft product (vendor only). Only draft products can be deleted.",
    parameters=[
        OpenApiParameter(name='slug', description='Product slug', required=True, type=str)
    ],
    responses={
        200: {"description": "Product deleted successfully"},
        404: {"description": "Product not found"},
        403: {"description": "Permission denied or product not a draft"}
    }
)
class DeleteDraftProductView(BaseAPIView):
    """
    Delete a draft product.
    Only available for products in draft status.
    Only the vendor who created the product can delete it.
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def delete(self, request, slug):
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response(
                standardized_response(success=False, error="Product not found"),
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if user is the vendor who owns this product
        from users.services.profile_resolver import ProfileResolver
        vendor = ProfileResolver.resolve_vendor(request.user)
        
        if vendor is None or product.store != vendor:
            return Response(
                standardized_response(success=False, error="You don't have permission to delete this product"),
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if product is in draft status
        if product.publish_status != 'draft':
            return Response(
                standardized_response(
                    success=False,
                    error=f"Only draft products can be deleted. This product is {product.publish_status}"
                ),
                status=status.HTTP_400_BAD_REQUEST
            )

        product_name = product.name
        product.delete()

        return Response(
            standardized_response(
                message=f"Draft product '{product_name}' deleted successfully"
            ),
            status=status.HTTP_200_OK
        )

# ==========================================
# CATEGORY VIEWS
# ==========================================
class CategoryListCreateView(BaseAPIView, generics.ListCreateAPIView):
    """
    Get list of all categories or create a new category (admin only).
    
    GET /categories - Returns all categories with product counts and sales
    POST /categories - Create a new category (admin only)
    """
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]  # GET is public, POST requires admin check
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_permissions(self):
        """Allow public GET, but restrict POST to admins"""
        if self.request.method == 'POST':
            return [IsAdmin()]
        return [AllowAny()]

    @extend_schema(
        summary="List all active categories",
        description="Returns all active categories with aggregated product counts and total sales.",
        responses={200: CategorySerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a new category",
        description="Admin only: Create a new product category.",
        request=CategorySerializer,
        responses={201: CategorySerializer}
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        """Track admin who created the category"""
        serializer.save()


class CategoryDetailView(BaseAPIView, generics.RetrieveUpdateDestroyAPIView):
    """
    Get, update, or delete a specific category (admin only for update/delete).
    
    GET /categories/:slug - Get category details
    PATCH /categories/:slug - Update category (admin only)
    DELETE /categories/:slug - Delete category (admin only)
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_permissions(self):
        """Allow public GET, but restrict PATCH/DELETE to admins"""
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdmin()]

    @extend_schema(
        summary="Retrieve category details",
        description="Get detailed information about a specific category including product counts and sales.",
        responses={200: CategorySerializer}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update category",
        description="Admin only: Update category details.",
        request=CategorySerializer,
        responses={200: CategorySerializer}
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        summary="Delete category",
        description="Admin only: Delete a category. Associated products will have null category.",
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)


# ==========================================
# PRODUCT STATISTICS VIEW
# ==========================================
class ProductStatsView(BaseAPIView):
    """
    Get dashboard statistics for products.
    
    GET /products/stats - Returns counts for dashboard cards:
    - totalProducts: Approved and submitted products
    - approvedCount: Products with approved status
    - rejectedCount: Products with rejected status
    - pendingCount: Products with pending status
    - draftCount: Draft products (admin/vendor only)
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Get product statistics",
        description="Returns aggregated product counts by approval status for dashboard display.",
        responses={
            200: {
                "type": "object",
                "properties": {
                    "total_products": {"type": "integer", "description": "Total approved products"},
                    "approved_count": {"type": "integer"},
                    "rejected_count": {"type": "integer"},
                    "pending_count": {"type": "integer"},
                    "draft_count": {"type": "integer"}
                }
            }
        }
    )
    def get(self, request):
        """Get product statistics"""
        stats = {
            'total_products': Product.objects.filter(
                approval_status='approved',
                publish_status='submitted'
            ).count(),
            'approved_count': Product.objects.filter(approval_status='approved').count(),
            'rejected_count': Product.objects.filter(approval_status='rejected').count(),
            'pending_count': Product.objects.filter(approval_status='pending').count(),
            'draft_count': Product.objects.filter(publish_status='draft').count(),
        }
        
        return Response(
            standardized_response(data=stats),
            status=status.HTTP_200_OK
        )


# ==========================================
# PRODUCT FILTERING & ADVANCED VIEWS
# ==========================================
class ProductFilteredView(BaseAPIView, generics.ListAPIView):
    """
    Get products with advanced filtering options.
    
    GET /products/filtered - Returns filtered products with support for:
    - status: Filter by approval status (approved, pending, rejected)
    - category: Filter by category ID or slug
    - vendor: Filter by vendor/store ID
    - search: Search in product name and description
    - ordering: Sort by price, name, created_at, etc.
    """
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'store', 'approval_status']
    search_fields = ['name', 'description', 'brand']
    ordering_fields = ['price', 'name', 'created_at', 'approval_status']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Return products based on filters.
        Default shows only approved products.
        """
        queryset = Product.objects.all()
        
        # Check if user is admin
        from authentication.core.permissions import IsAdmin
        is_admin = IsAdmin().has_permission(self.request, self) if self.request.user.is_authenticated else False
        
        # Only show approved published products by default for public users
        if not is_admin:
            queryset = queryset.filter(
                approval_status='approved',
                publish_status='submitted'
            )
        
        # Allow filtering by status if user has permission
        status_filter = self.request.query_params.get('status', None)
        if status_filter and self.request.user.is_authenticated and is_admin:
            queryset = queryset.filter(approval_status=status_filter)
        
        return queryset

    @extend_schema(
        summary="Get filtered products",
        description="Returns products with advanced filtering and sorting options.",
        parameters=[
            OpenApiParameter(name='status', description='Filter by approval status: approved, pending, rejected', required=False),
            OpenApiParameter(name='category', description='Filter by category ID', required=False),
            OpenApiParameter(name='store', description='Filter by vendor/store ID', required=False),
            OpenApiParameter(name='search', description='Search in product name and description', required=False),
            OpenApiParameter(name='ordering', description='Sort by: price, name, created_at', required=False),
        ],
        responses={200: ProductSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# ==========================================
# PRODUCT SUMMARY & DASHBOARD VIEWS
# ==========================================
@extend_schema(
    tags=["Products - Dashboard"],
    summary="Get product summary statistics",
    description="Returns total count of products by approval status for dashboard display. This endpoint provides the main dashboard card data.",
    responses={
        200: {
            "type": "object",
            "properties": {
                "total": {"type": "integer", "description": "Total approved and submitted products"},
                "approved": {"type": "integer", "description": "Products with approved status"},
                "rejected": {"type": "integer", "description": "Products with rejected status"},
                "pending": {"type": "integer", "description": "Products with pending approval status"}
            }
        }
    }
)
class ProductSummaryView(BaseAPIView):
    """
    Get product dashboard summary.
    Returns total counts of products categorized by approval status.
    Main endpoint for dashboard card data.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        """Get product summary statistics"""
        summary = {
            'total': Product.objects.filter(
                approval_status='approved',
                publish_status='submitted'
            ).count(),
            'approved': Product.objects.filter(approval_status='approved').count(),
            'rejected': Product.objects.filter(approval_status='rejected').count(),
            'pending': Product.objects.filter(approval_status='pending').count(),
        }
        
        return Response(
            standardized_response(
                data=summary,
                message="Product summary retrieved successfully"
            ),
            status=status.HTTP_200_OK
        )


# ==========================================
# PRODUCT REVIEW/APPROVAL WORKFLOW
# ==========================================
@extend_schema(
    tags=["Admin - Product Review"],
    summary="Review a product (approve or reject)",
    description="Admin endpoint to review and approve or reject a pending product. Updates product status and sends notification to vendor.",
    parameters=[
        OpenApiParameter(name='id', description='Product ID', required=True, type=int)
    ],
    request=ProductApprovalSerializer,
    responses={
        200: {"description": "Product reviewed successfully"},
        400: {"description": "Invalid request or missing required fields"},
        404: {"description": "Product not found"},
        403: {"description": "Only admin can review products"}
    }
)
class ProductReviewView(BaseAPIView):
    """
    Admin endpoint to review a product and change its approval status.
    Supports both approval and rejection with optional reason.
    Sends email notification to vendor.
    """
    permission_classes = [IsAdmin]

    def post(self, request, id):
        """Review a product (approve or reject)"""
        try:
            product = Product.objects.get(id=id)
        except Product.DoesNotExist:
            return Response(
                standardized_response(success=False, error="Product not found"),
                status=status.HTTP_404_NOT_FOUND
            )

        # Get status and reason from request
        status_action = request.data.get('status', '').lower()
        reason = request.data.get('reason', '')

        # Validate status field
        if status_action not in ['approved', 'rejected']:
            return Response(
                standardized_response(
                    success=False, 
                    error="Status must be 'approved' or 'rejected'"
                ),
                status=status.HTTP_400_BAD_REQUEST
            )

        # For rejection, reason is required
        if status_action == 'rejected' and not reason:
            return Response(
                standardized_response(
                    success=False,
                    error="Reason is required when rejecting a product"
                ),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update product
        product.approval_status = status_action
        product.approved_by = request.user
        product.approval_date = timezone.now()
        
        if status_action == 'rejected':
            product.rejection_reason = reason
        else:
            product.rejection_reason = None
            
        product.save()

        # Send email notification to vendor
        from store.tasks import send_product_approval_email_task, send_product_rejection_email_task
    
        if status_action == 'approved':
            send_product_approval_email_task.delay(product.id)
        else:
            send_product_rejection_email_task.delay(product.id, reason)

        serializer = PendingProductsSerializer(product)
        return Response(
            standardized_response(
                data=serializer.data,
                message=f"Product '{product.name}' {status_action} successfully"
            ),
            status=status.HTTP_200_OK
        )


# ==========================================
# VENDOR ADMIN - PRODUCT DETAILS
# ==========================================
class VendorAdminProductDetailView(BaseAPIView):
    """
    Vendor admin endpoint to view detailed product information.
    Returns comprehensive product details including vendor information and approval status.
    
    Accessible by: Vendor (viewing own products) or Admin (viewing all products)
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Vendor Admin - Products"],
        summary="Get Product Details",
        description="Retrieve detailed information for a specific product by slug. Includes vendor details, pricing, stock, and approval status.",
        parameters=[
            OpenApiParameter(
                name='slug', 
                description='Product slug identifier', 
                required=True, 
                type=str,
                location=OpenApiParameter.PATH
            )
        ],
        responses={
            200: OpenApiResponse(
                description="Product details retrieved successfully",
                response=VendorAdminProductDetailSerializer
            ),
            404: OpenApiResponse(description="Product not found"),
            403: OpenApiResponse(description="Not authorized to view this product")
        }
    )
    def get(self, request, slug):
        """
        Get detailed product information for vendor admin dashboard.
        
        Returns product with full vendor details, image URL, and status.
        Vendors can only view their own products; admins can view all.
        """
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response(
                standardized_response(
                    success=False, 
                    error="Product not found"
                ),
                status=status.HTTP_404_NOT_FOUND
            )

        # Check authorization: vendor can only view own products, admin can view all
        from authentication.core.permissions import IsVendor
        is_admin = hasattr(request.user, 'business_admin_profile')
        is_vendor = hasattr(request.user, 'vendor_profile')

        if is_vendor and not is_admin:
            # Vendor can only view their own products
            if product.store.user != request.user:
                return Response(
                    standardized_response(
                        success=False,
                        error="Not authorized to view this product"
                    ),
                    status=status.HTTP_403_FORBIDDEN
                )
        elif not is_admin:
            # Non-admin, non-vendor users cannot view
            return Response(
                standardized_response(
                    success=False,
                    error="Not authorized to view this product"
                ),
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = VendorAdminProductDetailSerializer(product)
        return Response(
            standardized_response(
                success=True,
                data=serializer.data
            ),
            status=status.HTTP_200_OK
        )