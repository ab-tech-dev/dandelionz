from rest_framework import serializers
from .models import Product, Cart, CartItem, Favourite, Review
from authentication.models import CustomUser
from users.models import Vendor

CLOUDINARY_BASE_URL = "https://res.cloudinary.com/dhpny4uce/"


# ---------------------------
# Base Serializer with Cloudinary helper
# ---------------------------
class CloudinarySerializer(serializers.ModelSerializer):
    def get_cloudinary_url(self, field_value):
        if field_value:
            return f"{CLOUDINARY_BASE_URL}{field_value}"
        return None




# ---------------------------
# Review Serializer
# ---------------------------
class ReviewSerializer(CloudinarySerializer):
    customer_name = serializers.CharField(source='customer.full_name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = Review
        fields = [
            'id', 'product', 'product_name', 'customer', 'customer_name',
            'rating', 'comment', 'created_at', 'updated_at'
        ]


# ---------------------------
# Product Serializer
# ---------------------------
class ProductSerializer(CloudinarySerializer):
    store_name = serializers.CharField(source='store.store_name', read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'store', 'store_name', 'name', 'slug', 'description', 'category',
            'price', 'discounted_price', 'stock', 'brand', 'tags', 'variants', 'image', 
            'in_stock', 'created_at', 'updated_at', 'reviews'
        ]
        ref_name = "StoreProductSerializer"

    def get_image(self, obj):
        return self.get_cloudinary_url(obj.image)

class CreateProductSerializer(CloudinarySerializer):
    store = serializers.CharField(source='store.store_name', read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'description', 'category',
            'price', 'discounted_price', 'stock', 'brand', 'tags', 'variants', 'image', 'store', 
            'publish_status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'store', 'publish_status', 'created_at', 'updated_at']

    def get_image(self, obj):
        return self.get_cloudinary_url(obj.image)



# ---------------------------
# Cart Item Serializer
# ---------------------------
class CartItemSerializer(CloudinarySerializer):
    product_details = ProductSerializer(source='product', read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_details', 'quantity', 'subtotal']


# ---------------------------
# Cart Serializer
# ---------------------------
class CartSerializer(CloudinarySerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'customer', 'items', 'total', 'created_at', 'updated_at']


# ---------------------------
# Favourite Serializer
# ---------------------------
class FavouriteSerializer(CloudinarySerializer):
    product_details = ProductSerializer(source='product', read_only=True)

    class Meta:
        model = Favourite
        fields = ['id', 'customer', 'product', 'product_details', 'added_at']


# ---------------------------
# Admin Product Approval Serializers
# ---------------------------
class PendingProductsSerializer(CloudinarySerializer):
    """
    Serializer for displaying products pending approval.
    Includes approval status and admin details.
    """
    store_name = serializers.CharField(source='store.store_name', read_only=True)
    store_owner_email = serializers.CharField(source='store.user.email', read_only=True)
    approved_by_email = serializers.CharField(source='approved_by.email', read_only=True, allow_null=True)
    in_stock = serializers.BooleanField(read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'store', 'store_name', 'store_owner_email', 'name', 'slug', 
            'description', 'category', 'price', 'discounted_price', 'stock', 
            'brand', 'tags', 'variants', 'image', 'in_stock',
            'publish_status', 'approval_status', 'approved_by', 'approved_by_email', 'approval_date', 
            'rejection_reason', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'publish_status', 'approval_status', 'approved_by', 'approval_date', 
            'rejection_reason', 'created_at', 'updated_at'
        ]

    def get_image(self, obj):
        return self.get_cloudinary_url(obj.image)


class ProductApprovalSerializer(serializers.Serializer):
    """
    Serializer for approving or rejecting a product.
    Used for validation of approval/rejection requests.
    """
    rejection_reason = serializers.CharField(
        max_length=1000, 
        required=False, 
        allow_blank=False,
        help_text="Reason for rejecting the product (required for rejection)"
    )

    class Meta:
        fields = ['rejection_reason']

