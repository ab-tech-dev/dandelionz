from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import PermissionDenied
from .models import Product
from authentication.core.base_view import BaseAPIView
from .serializers import  ProductSerializer
from authentication.core.response import standardized_response
from rest_framework.response import Response
from rest_framework import generics
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse
from django.utils import timezone

from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Product, Cart, CartItem, Favourite, Review
from .serializers import (
    ProductSerializer, CreateProductSerializer, CartSerializer, CartItemSerializer,
    FavouriteSerializer, ReviewSerializer, ProductApprovalSerializer, PendingProductsSerializer
)

from rest_framework import serializers
from authentication.core.base_view import BaseAPIView
from authentication.core.response import standardized_response
from authentication.core.permissions import IsAdminOrVendor, IsAdmin, IsVendor

# ---------------------------
# Products List & Filtering
# ---------------------------
class ProductListView(BaseAPIView, generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['store', 'price', 'category']
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
            OpenApiParameter(name='price', description='Filter by price', required=False, type=float),
            OpenApiParameter(name='category', description='Filter by category', required=False, type=str),
            OpenApiParameter(name='search', description='Search by name or description', required=False, type=str),
            OpenApiParameter(name='ordering', description='Order by price or name', required=False, type=str),
        ],
        responses={200: ProductSerializer(many=True)},
        description="Retrieve a list of products. Supports filtering, search, and ordering. Only shows approved products."
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
    description="Create a new product as draft (authenticated users only). Product starts as draft and won't be submitted for approval until vendor submits it.",
    request=ProductSerializer,
    examples=[
        OpenApiExample(
            "Create product example",
            summary="Add new product as draft",
            value={
                "name": "Example Product",
                "description": "Product description",
                "price": 100.0,
                "category": "electronics",
                "stock": 10,
                "image": None
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
    parameters=[OpenApiParameter(name='product_id', description='Product ID to remove', required=True, type=int)],
    responses={
        200: {"description": "Item removed successfully"},
        404: {"description": "Item not found in cart"}
    },
)
class RemoveFromCartView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, product_id):
        cart = get_object_or_404(Cart, customer=request.user)
        item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
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
    parameters=[OpenApiParameter(name='product_id', description='Product ID to remove', required=True, type=int)],
    responses={
        200: {"description": "Removed successfully"},
        404: {"description": "Product not in favourites"}
    }
)
class RemoveFavouriteView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, product_id):
        fav = Favourite.objects.filter(customer=request.user, product_id=product_id).first()
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
        OpenApiParameter(name='product_id', description='Product ID', required=True, type=int)
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

    def post(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
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
        OpenApiParameter(name='product_id', description='Product ID', required=True, type=int)
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

    def post(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
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
        OpenApiParameter(name='product_id', description='Product ID', required=True, type=int)
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

    def post(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
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
        OpenApiParameter(name='product_id', description='Product ID', required=True, type=int)
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

    def patch(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
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
        OpenApiParameter(name='product_id', description='Product ID', required=True, type=int)
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

    def delete(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
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
