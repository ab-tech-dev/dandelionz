from rest_framework import serializers
from .models import Product, Cart, CartItem, Favourite, Review, Category, ProductImage, ProductVideo
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
# Product Image Serializer
# ---------------------------
class ProductImageSerializer(CloudinarySerializer):
    """
    Serializer for product images with variant association.
    """
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = [
            'id', 'image', 'image_url', 'is_main', 'alt_text', 
            'variant_association', 'display_order', 'uploaded_at', 'updated_at'
        ]
        read_only_fields = ['id', 'uploaded_at', 'updated_at']

    def get_image_url(self, obj):
        return self.get_cloudinary_url(obj.image)


class ProductImageCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating product images.
    Used in product creation workflow.
    """
    class Meta:
        model = ProductImage
        fields = ['image', 'is_main', 'alt_text', 'variant_association', 'display_order']


# ---------------------------
# Product Video Serializer
# ---------------------------
class ProductVideoSerializer(CloudinarySerializer):
    """
    Serializer for product videos.
    """
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductVideo
        fields = [
            'id', 'video', 'video_url', 'title', 'description', 
            'duration', 'file_size', 'uploaded_at', 'updated_at'
        ]
        read_only_fields = ['id', 'duration', 'file_size', 'uploaded_at', 'updated_at']

    def get_video_url(self, obj):
        return self.get_cloudinary_url(obj.video)


class ProductVideoCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating product videos.
    Used in product creation workflow.
    """
    class Meta:
        model = ProductVideo
        fields = ['video', 'title', 'description']


# ---------------------------
# Review Serializer
# ---------------------------
class ReviewSerializer(CloudinarySerializer):
    customer_name = serializers.CharField(source='customer.full_name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    customer = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Review
        fields = [
            'id', 'product', 'product_name', 'customer', 'customer_name',
            'rating', 'comment', 'created_at', 'updated_at'
        ]

    def validate_rating(self, value):
        """Validate rating is between 1 and 5"""
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value


# ---------------------------
# Product Serializer
# ---------------------------
class ProductSerializer(CloudinarySerializer):
    vendor = VendorSerializer(source='store', read_only=True)
    vendorName = serializers.CharField(source='store.store_name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    category = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Category.objects.all(),
        required=False,
        allow_null=True
    )
    in_stock = serializers.BooleanField(read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    videos = ProductVideoSerializer(many=True, read_only=True)
    image = serializers.SerializerMethodField()
    uploaded_date = serializers.DateTimeField(source='created_at', read_only=True)
    rating = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'vendor', 'vendorName', 'name', 'slug', 'description', 'category',
            'category_name', 'price', 'discount', 'stock', 'brand', 'tags', 
            'variants', 'image', 'images', 'videos', 'in_stock', 'approval_status', 'uploaded_date', 
            'created_at', 'updated_at', 'reviews', 'rating'
        ]
        ref_name = "StoreProductSerializer"

    def get_image(self, obj):
        # Return main image if available, otherwise first image
        main_image = obj.main_image
        if main_image:
            return self.get_cloudinary_url(main_image.image)
        return None

    def get_rating(self, obj):
        """Calculate average rating from reviews"""
        from django.db.models import Avg
        avg_rating = obj.reviews.aggregate(Avg('rating'))['rating__avg']
        return round(avg_rating, 2) if avg_rating else None

class CreateProductSerializer(CloudinarySerializer):
    """
    Serializer for creating draft products with images and optional video.
    
    Vendor can provide:
    - Basic product info (name, description, price, etc.)
    - At least one image (required) with optional variant associations
    - Optional video (max 5MB)
    - Images can be marked as main or associated with specific variants
    """
    vendorName = serializers.CharField(source='store.store_name', read_only=True)
    image = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    videos = ProductVideoSerializer(many=True, read_only=True)
    
    # Nested serializers for creating related objects
    images_data = ProductImageCreateSerializer(many=True, write_only=True, required=False, help_text="List of images for the product. At least one image is required.")
    video_data = ProductVideoCreateSerializer(write_only=True, required=False, allow_null=True, help_text="Optional video for the product (max 5MB)")
    
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
            'price', 'discount', 'stock', 'tags', 'variants', 'image', 
            'images', 'videos', 'images_data', 'video_data',
            'vendorName', 'in_stock', 'publish_status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'vendorName', 'in_stock', 'created_at', 'updated_at', 'images', 'videos']

    def get_image(self, obj):
        # Return main image if available, otherwise first image
        main_image = obj.main_image
        if main_image:
            return self.get_cloudinary_url(main_image.image)
        return None

    def validate_images_data(self, value):
        """Validate that at least one image is provided and at least one is marked as main"""
        if not value:
            raise serializers.ValidationError("At least one image is required")
        
        # Check if at least one image is marked as main
        has_main = any(img.get('is_main', False) for img in value)
        if not has_main:
            raise serializers.ValidationError("At least one image must be marked as main (is_main: true)")
        
        return value

    def validate_video_data(self, value):
        """Validate video file size doesn't exceed 5MB"""
        if not value:
            return value
        
        from .models import validate_video_size
        
        # Get file size from uploaded file if available
        if hasattr(value.get('video'), 'size'):
            is_valid, error_msg = validate_video_size(value['video'].size)
            if not is_valid:
                raise serializers.ValidationError({"video": error_msg})
        
        return value

    def validate(self, data):
        """Cross-field validation"""
        # Validate variant associations if variants exist
        if data.get('variants'):
            images_data = self.initial_data.get('images_data', [])
            from .models import validate_variant_association
            
            for img in images_data:
                variant_assoc = img.get('variant_association')
                if variant_assoc:
                    is_valid, error_msg = validate_variant_association(variant_assoc, data['variants'])
                    if not is_valid:
                        raise serializers.ValidationError({"images_data": error_msg})
        
        return data


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
    slug = serializers.SlugRelatedField(
        slug_field='slug',
        source='product',
        queryset=Product.objects.all(),
        write_only=True,
        required=False
    )

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_details', 'slug', 'quantity', 'subtotal']
        read_only_fields = ['id', 'product', 'product_details', 'subtotal']


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
    slug = serializers.SlugRelatedField(
        slug_field='slug',
        source='product',
        queryset=Product.objects.all(),
        write_only=True,
        required=False
    )

    class Meta:
        model = Favourite
        fields = ['id', 'customer', 'product', 'product_details', 'slug', 'added_at']
        read_only_fields = ['id', 'customer', 'product', 'product_details', 'added_at']


# ---------------------------
# Admin Product Approval Serializers
# ---------------------------
class PendingProductsSerializer(CloudinarySerializer):
    """
    Serializer for displaying products pending approval.
    Includes approval status, admin details, and product media.
    """
    vendor = VendorSerializer(source='store', read_only=True)
    vendorName = serializers.CharField(source='store.store_name', read_only=True)
    store_owner_email = serializers.CharField(source='store.user.email', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    approved_by_email = serializers.CharField(source='approved_by.email', read_only=True, allow_null=True)
    in_stock = serializers.BooleanField(read_only=True)
    image = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)
    videos = ProductVideoSerializer(many=True, read_only=True)
    uploaded_date = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'store', 'vendor', 'vendorName', 'store_owner_email', 'name', 'slug', 
            'description', 'category', 'category_name', 'price', 'discount', 'stock', 
            'brand', 'tags', 'variants', 'image', 'images', 'videos', 'in_stock', 'uploaded_date',
            'publish_status', 'approval_status', 'approved_by', 'approved_by_email', 'approval_date', 
            'rejection_reason', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'publish_status', 'approval_status', 'approved_by', 'approval_date', 
            'rejection_reason', 'created_at', 'updated_at'
        ]

    def get_image(self, obj):
        # Return main image if available
        main_image = obj.main_image
        if main_image:
            return self.get_cloudinary_url(main_image.image)
        return None


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


# ---------------------------
# Vendor Admin Product Detail Serializer
# ---------------------------
class VendorAdminProductDetailSerializer(CloudinarySerializer):
    """
    Serializer for vendor admin to view detailed product information.
    Includes full vendor details, approval status, product attributes, and media.
    Used for GET /user/admin/products/{slug}/
    """
    vendor = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    in_stock = serializers.BooleanField(read_only=True)
    image = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)
    videos = ProductVideoSerializer(many=True, read_only=True)
    uploadDate = serializers.DateTimeField(source='created_at', read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'slug', 'name', 'description', 'price', 'category',
            'category_name', 'stock', 'in_stock', 'image', 'images', 'videos', 'uploadDate', 'vendor', 'status'
        ]
        read_only_fields = fields

    def get_vendor(self, obj):
        """
        Format vendor information according to spec.
        Returns vendor UUID, store_name, and email.
        """
        return {
            'uuid': str(obj.store.user.uuid),
            'store_name': obj.store.store_name,
            'email': obj.store.user.email
        }

    def get_image(self, obj):
        """Convert CloudinaryField to URL - return main image"""
        main_image = obj.main_image
        if main_image:
            return f"{CLOUDINARY_BASE_URL}{main_image.image}"
        return None

    def get_status(self, obj):
        """
        Convert approval_status to uppercase format.
        Choices: 'pending', 'approved', 'rejected' -> 'PENDING', 'APPROVED', 'REJECTED'
        """
        status_map = {
            'pending': 'PENDING',
            'approved': 'APPROVED',
            'rejected': 'REJECTED'
        }
        return status_map.get(obj.approval_status, obj.approval_status.upper())

