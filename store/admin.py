from django.contrib import admin
from .models import Product, Cart, CartItem, Favourite, Review, Category


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
    list_display = ('name', 'store', 'category', 'price', 'discounted_price', 'brand', 'stock', 'in_stock', 'approval_status', 'created_at')
    list_filter = ('category', 'created_at', 'store', 'brand', 'approval_status')
    search_fields = ('name', 'description', 'brand', 'tags')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('slug', 'created_at', 'updated_at', 'approved_by', 'approval_date')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'store', 'category', 'brand')
        }),
        ('Details', {
            'fields': ('description', 'price', 'discounted_price', 'stock', 'image')
        }),
        ('Product Attributes', {
            'fields': ('tags', 'variants'),
            'description': 'Tags: comma-separated or JSON array. Variants: JSON with color and/or size.'
        }),
        ('Approval Status', {
            'fields': ('approval_status', 'approved_by', 'approval_date', 'rejection_reason'),
            'description': 'Manage product approval. Pending products must be approved before they appear in customer listings.'
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
