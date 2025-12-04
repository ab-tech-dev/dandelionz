from rest_framework import serializers
from .models import Product, Cart, CartItem, Favourite, Review
from authentication.models import CustomUser
from users.models import Vendor



# ---------------------------
# Review Serializer
# ---------------------------
class ReviewSerializer(serializers.ModelSerializer):
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
class ProductSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.store_name', read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)  # <-- ADD THIS

    class Meta:
        model = Product
        fields = [
            'id', 'store', 'store_name', 'name', 'slug', 'description', 'category',
            'price', 'stock', 'image', 'in_stock', 'created_at', 'updated_at',
            'reviews'  # <-- ADD THIS
        ]
        ref_name = "StoreProductSerializer"



class CreateProductSerializer(serializers.ModelSerializer):
    # Make store read-only and automatically set from the vendor
    store = serializers.CharField(source='store.store_name', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'description', 'category',
            'price', 'stock', 'image', 'store', 'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'store', 'created_at', 'updated_at']



# ---------------------------
# Cart Item Serializer
# ---------------------------
class CartItemSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source='product', read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_details', 'quantity', 'subtotal']


# ---------------------------
# Cart Serializer
# ---------------------------
class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'customer', 'items', 'total', 'created_at', 'updated_at']


# ---------------------------
# Favourite Serializer
# ---------------------------
class FavouriteSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source='product', read_only=True)

    class Meta:
        model = Favourite
        fields = ['id', 'customer', 'product', 'product_details', 'added_at']


