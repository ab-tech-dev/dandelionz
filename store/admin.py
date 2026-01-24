from django.contrib import admin
from .models import Product, Cart, CartItem, Favourite, Review, Category, ProductImage, ProductVideo


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_count', 'total_sales', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Category Information', {
            'fields': ('name', 'slug', 'description', 'image')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def product_count(self, obj):
        return obj.product_count
    product_count.short_description = 'Products'

    def total_sales(self, obj):
        return obj.total_sales
    total_sales.short_description = 'Total Sales'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'store', 'category', 'price', 'discounted_price', 'brand', 'stock', 'in_stock', 'approval_status', 'publish_status', 'created_at')
    list_filter = ('category', 'created_at', 'store', 'brand', 'approval_status', 'publish_status')
    search_fields = ('name', 'description', 'brand', 'tags')
    readonly_fields = ('slug', 'created_at', 'updated_at', 'approved_by', 'approval_date')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'store', 'category', 'brand')
        }),
        ('Details', {
            'fields': ('description', 'price', 'discounted_price', 'stock', 'image')
        }),
        ('Product Attributes', {
            'fields': ('tags', 'variants'),
            'description': 'Tags: comma-separated or JSON array. Variants: JSON with color and/or size.'
        }),
        ('Publishing & Approval', {
            'fields': ('publish_status', 'approval_status', 'approved_by', 'approval_date', 'rejection_reason'),
            'description': 'Publish Status: Set to "submitted" to make visible. Approval Status: Pending products must be approved before they appear in customer listings.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('customer', 'created_at', 'updated_at')
    list_filter = ('created_at',)
    search_fields = ('customer__email', 'customer__full_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'product', 'quantity', 'subtotal')
    list_filter = ('cart__customer',)
    search_fields = ('product__name',)


@admin.register(Favourite)
class FavouriteAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'added_at')
    list_filter = ('added_at',)
    search_fields = ('customer__email', 'product__name')
    readonly_fields = ('added_at',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'customer', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('product__name', 'customer__email')
    readonly_fields = ('created_at',)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'is_main', 'display_order', 'uploaded_at')
    list_filter = ('is_main', 'product', 'uploaded_at')
    search_fields = ('product__name', 'alt_text')
    readonly_fields = ('uploaded_at', 'updated_at')
    fieldsets = (
        ('Image Information', {
            'fields': ('product', 'image', 'alt_text', 'is_main')
        }),
        ('Display & Variants', {
            'fields': ('display_order', 'variant_association'),
            'description': 'Variant association is optional JSON mapping of variant attributes (e.g., {"colors": ["red", "blue"]})'
        }),
        ('Timestamps', {
            'fields': ('uploaded_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ProductVideo)
class ProductVideoAdmin(admin.ModelAdmin):
    list_display = ('product', 'title', 'duration', 'file_size', 'uploaded_at')
    list_filter = ('product', 'uploaded_at')
    search_fields = ('product__name', 'title', 'description')
    readonly_fields = ('uploaded_at', 'updated_at')
    fieldsets = (
        ('Video Information', {
            'fields': ('product', 'video', 'title', 'description')
        }),
        ('Metadata', {
            'fields': ('duration', 'file_size'),
            'description': 'Duration in seconds, file size in bytes'
        }),
        ('Timestamps', {
            'fields': ('uploaded_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
