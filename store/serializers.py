from rest_framework import serializers
from .models import Product, Cart, CartItem, Favourite, Review, Category
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
# Vendor Serializer
# ---------------------------
class VendorSerializer(serializers.ModelSerializer):
    """
    Serializer for Vendor information included in product responses.
    """
    email_address = serializers.CharField(source='user.email', read_only=True)
    store_name = serializers.CharField(read_only=True)
    
    class Meta:
        model = Vendor
        fields = [
            'id', 'store_name', 'email_address', 'vendor_status', 
            'store_description', 'address'
        ]


# ---------------------------
# Category Serializer
# ---------------------------
class CategorySerializer(CloudinarySerializer):
    """
    Serializer for Category model with aggregated stats.
    """
    product_count = serializers.SerializerMethodField()
    total_sales = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'image', 'is_active',
            'product_count', 'total_sales', 'created_at', 'updated_at'
        ]

    def get_product_count(self, obj):
        return obj.product_count

    def get_total_sales(self, obj):
        return obj.total_sales

    def get_image(self, obj):
        return self.get_cloudinary_url(obj.image)


class CategoryListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for category listings.
    """
    product_count = serializers.SerializerMethodField()
    total_sales = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'product_count', 'total_sales']

    def get_product_count(self, obj):
        return obj.product_count

    def get_total_sales(self, obj):
        return obj.total_sales




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
    vendor = VendorSerializer(source='store', read_only=True)
    vendorName = serializers.CharField(source='store.store_name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    image = serializers.SerializerMethodField()
    uploaded_date = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'store', 'vendor', 'vendorName', 'name', 'slug', 'description', 'category',
            'category_name', 'price', 'discounted_price', 'stock', 'brand', 'tags', 
            'variants', 'image', 'in_stock', 'approval_status', 'uploaded_date', 
            'created_at', 'updated_at', 'reviews'
        ]
        ref_name = "StoreProductSerializer"

    def get_image(self, obj):
        return self.get_cloudinary_url(obj.image)

class CreateProductSerializer(CloudinarySerializer):
    """
    Serializer for creating draft products.
    Vendor can provide all product information which will be saved as draft.
    """
    vendorName = serializers.CharField(source='store.store_name', read_only=True)
    image = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    category = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Category.objects.all(),
        required=False,
        allow_null=True,
        help_text="Category slug (string)"
    )

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'brand',
            'price', 'discounted_price', 'stock', 'tags', 'variants', 'image', 
            'vendorName', 'in_stock', 'publish_status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'vendorName', 'in_stock', 'publish_status', 'created_at', 'updated_at']

    def get_image(self, obj):
        return self.get_cloudinary_url(obj.image)


# ---------------------------
# Dashboard Stats Serializers
# ---------------------------
class ProductStatsSerializer(serializers.Serializer):
    """
    Serializer for product dashboard statistics.
    Used for the stats endpoint showing counts by approval status.
    """
    total_products = serializers.IntegerField(help_text="Total number of approved and submitted products")
    approved_count = serializers.IntegerField(help_text="Number of approved products")
    rejected_count = serializers.IntegerField(help_text="Number of rejected products")
    pending_count = serializers.IntegerField(help_text="Number of pending products")
    draft_count = serializers.IntegerField(help_text="Number of draft products")


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
    vendor = VendorSerializer(source='store', read_only=True)
    vendorName = serializers.CharField(source='store.store_name', read_only=True)
    store_owner_email = serializers.CharField(source='store.user.email', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    approved_by_email = serializers.CharField(source='approved_by.email', read_only=True, allow_null=True)
    in_stock = serializers.BooleanField(read_only=True)
    image = serializers.SerializerMethodField()
    uploaded_date = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'store', 'vendor', 'vendorName', 'store_owner_email', 'name', 'slug', 
            'description', 'category', 'category_name', 'price', 'discounted_price', 'stock', 
            'brand', 'tags', 'variants', 'image', 'in_stock', 'uploaded_date',
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

