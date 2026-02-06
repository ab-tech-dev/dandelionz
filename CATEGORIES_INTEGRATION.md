# Categories Integration Guide (REST)

Base API:
- `https://api.dandelionz.com.ng`

All admin actions require:
- `Authorization: Bearer <admin_token>`

---
**Endpoints**

- `POST /store/categories/` (admin only)
- `PATCH /store/categories/{slug}/` (admin only)
- `GET /store/categories/{slug}/`
- `GET /store/categories/`
- `DELETE /store/categories/{slug}/` (admin only)

---
**1) Create Category**

**Multipart (with image)**
```bash
curl -X POST "https://api.dandelionz.com.ng/store/categories/" \
  -H "Authorization: Bearer <admin_token>" \
  -F "name=Electronics" \
  -F "description=Devices and accessories" \
  -F "image=@/path/to/category.jpg"
```

**JSON (without image)**
```json
{
  "name": "Electronics",
  "description": "Devices and accessories"
}
```

**Response (201)**
```json
{
  "id": 12,
  "name": "Electronics",
  "slug": "electronics",
  "description": "Devices and accessories",
  "image": "https://res.cloudinary.com/dhpny4uce/.../category.jpg",
  "is_active": true,
  "product_count": 0,
  "total_sales": 0,
  "created_at": "2026-02-06T10:00:00Z",
  "updated_at": "2026-02-06T10:00:00Z"
}
```

---
**2) Update Category**

**Multipart (with image)**
```bash
curl -X PATCH "https://api.dandelionz.com.ng/store/categories/electronics/" \
  -H "Authorization: Bearer <admin_token>" \
  -F "name=Electronics & Gadgets" \
  -F "description=Updated description" \
  -F "image=@/path/to/new-category.jpg"
```

**JSON**
```json
{
  "name": "Electronics & Gadgets",
  "description": "Updated description",
  "is_active": true
}
```

**Response (200)**
```json
{
  "id": 12,
  "name": "Electronics & Gadgets",
  "slug": "electronics",
  "description": "Updated description",
  "image": "https://res.cloudinary.com/dhpny4uce/.../category.jpg",
  "is_active": true,
  "product_count": 25,
  "total_sales": 1020,
  "created_at": "2026-02-06T10:00:00Z",
  "updated_at": "2026-02-06T10:10:00Z"
}
```

---
**3) Get Category**

`GET /store/categories/{slug}/`

**Response (200)**
```json
{
  "id": 12,
  "name": "Electronics",
  "slug": "electronics",
  "description": "Devices and accessories",
  "image": "https://res.cloudinary.com/dhpny4uce/.../category.jpg",
  "is_active": true,
  "product_count": 25,
  "total_sales": 1020,
  "created_at": "2026-02-06T10:00:00Z",
  "updated_at": "2026-02-06T10:00:00Z"
}
```

---
**4) List Categories**

`GET /store/categories/`

**Response (200)**
```json
[
  {
    "id": 12,
    "name": "Electronics",
    "slug": "electronics",
    "description": "Devices and accessories",
    "image": "https://res.cloudinary.com/dhpny4uce/.../category.jpg",
    "is_active": true,
    "product_count": 25,
    "total_sales": 1020,
    "created_at": "2026-02-06T10:00:00Z",
    "updated_at": "2026-02-06T10:00:00Z"
  }
]
```

---
**5) Delete Category**

`DELETE /store/categories/{slug}/`

**Response (204 No Content)**
```json
{"detail": "Category deleted"}
```

---
**Notes**
- `image` is optional; use `multipart/form-data` when uploading files.
- `is_active` defaults to `true` on create if not provided.
