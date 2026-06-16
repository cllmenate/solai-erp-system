from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.pagination import LimitOffsetPagination, paginate

from apps.assets.models import Batch, Brand, Category, Item, Model, TechSheetTemplate
from apps.core.auth import JWTAuth

router = Router(auth=JWTAuth())

# --- Basic Message Schema ---
class MessageSchema(Schema):
    message: str


# --- Brand Schemas ---
class BrandInputSchema(Schema):
    name: str
    website: str | None = None


class BrandSchema(Schema):
    id: UUID
    name: str
    description: str | None = None
    is_active: bool
    website: str | None = None


# --- TechSheetTemplate Schemas ---
class TechSheetTemplateInputSchema(Schema):
    name: str
    template_type: str = "custom"
    fields_schema: dict = {}
    description: str | None = None


class TechSheetTemplateSchema(Schema):
    id: UUID
    name: str
    description: str | None = None
    is_active: bool
    template_type: str
    fields_schema: dict


# --- Category Schemas ---
class CategoryInputSchema(Schema):
    name: str
    parent_id: UUID | None = None
    tech_sheet_template_ids: list[UUID] = []
    description: str | None = None


class CategorySchema(Schema):
    id: UUID
    name: str
    description: str | None = None
    is_active: bool
    parent_id: UUID | None = None
    tech_sheet_templates: list[TechSheetTemplateSchema]


# --- Model Schemas ---
class ModelInputSchema(Schema):
    name: str
    brand_id: UUID
    category_ids: list[UUID]
    unit_of_measure: str
    weight: float | None = None
    tech_sheet_template_ids: list[UUID] = []
    description: str | None = None


class ModelSchema(Schema):
    id: UUID
    name: str
    description: str | None = None
    is_active: bool
    brand: BrandSchema
    categories: list[CategorySchema]
    unit_of_measure: str
    weight: float | None = None
    tech_sheet_templates: list[TechSheetTemplateSchema]


# --- Item Schemas ---
class ItemInputSchema(Schema):
    model_id: UUID
    item_type: str
    ncm: str | None = None
    sku: str | None = None
    barcode: str | None = None
    serial_number: str | None = None
    acquisition_price: float = 0.0
    sale_price: float = 0.0
    description: str | None = None


class ItemSchema(Schema):
    id: UUID
    name: str
    description: str | None = None
    is_active: bool
    model: ModelSchema
    item_type: str
    ncm: str | None = None
    sku: str
    barcode: str
    serial_number: str | None = None
    acquisition_price: float
    sale_price: float


# --- Batch Schemas ---
class BatchInputSchema(Schema):
    item_id: UUID
    batch_code: str
    manufacture_date: str  # YYYY-MM-DD
    expiry_date: str  # YYYY-MM-DD
    total_quantity: float
    stock_quantity: float
    status: str = "active"
    description: str | None = None


class BatchSchema(Schema):
    id: UUID
    name: str
    description: str | None = None
    is_active: bool
    item_id: UUID
    batch_code: str
    manufacture_date: str
    expiry_date: str
    total_quantity: float
    stock_quantity: float
    status: str


# ================= BRAND ENDPOINTS =================

@router.get("/brands", response=list[BrandSchema])
@paginate(LimitOffsetPagination)
def list_brands(request, is_active: bool | None = None):
    qs = Brand.objects.filter(tenant=request.tenant)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs


@router.get("/brands/{brand_id}", response=BrandSchema)
def get_brand(request, brand_id: UUID):
    return get_object_or_404(Brand, id=brand_id, tenant=request.tenant)


@router.post("/brands", response={201: BrandSchema, 400: MessageSchema})
def create_brand(request, data: BrandInputSchema):
    try:
        brand = Brand.objects.create(
            tenant=request.tenant,
            name=data.name,
            website=data.website,
            created_by=request.auth,
            updated_by=request.auth,
        )
        return 201, brand
    except ValidationError as e:
        return 400, {"message": str(e)}


@router.put("/brands/{brand_id}", response={200: BrandSchema, 400: MessageSchema})
def update_brand(request, brand_id: UUID, data: BrandInputSchema):
    brand = get_object_or_404(Brand, id=brand_id, tenant=request.tenant)
    try:
        brand.name = data.name
        brand.website = data.website
        brand.updated_by = request.auth
        brand.save()
        return 200, brand
    except ValidationError as e:
        return 400, {"message": str(e)}


@router.delete("/brands/{brand_id}", response={200: MessageSchema})
def delete_brand(request, brand_id: UUID):
    brand = get_object_or_404(Brand, id=brand_id, tenant=request.tenant)
    brand.is_active = False
    brand.save()
    return 200, {"message": "Marca desativada com sucesso."}


# ================= TEMPLATE ENDPOINTS =================

@router.get("/templates", response=list[TechSheetTemplateSchema])
@paginate(LimitOffsetPagination)
def list_templates(request, is_active: bool | None = None):
    qs = TechSheetTemplate.objects.filter(tenant=request.tenant)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs


@router.get("/templates/{template_id}", response=TechSheetTemplateSchema)
def get_template(request, template_id: UUID):
    return get_object_or_404(TechSheetTemplate, id=template_id, tenant=request.tenant)


@router.post("/templates", response={201: TechSheetTemplateSchema, 400: MessageSchema})
def create_template(request, data: TechSheetTemplateInputSchema):
    try:
        template = TechSheetTemplate.objects.create(
            tenant=request.tenant,
            name=data.name,
            template_type=data.template_type,
            fields_schema=data.fields_schema,
            description=data.description,
            created_by=request.auth,
            updated_by=request.auth,
        )
        return 201, template
    except ValidationError as e:
        return 400, {"message": str(e)}


@router.put("/templates/{template_id}", response={200: TechSheetTemplateSchema, 400: MessageSchema})
def update_template(request, template_id: UUID, data: TechSheetTemplateInputSchema):
    template = get_object_or_404(TechSheetTemplate, id=template_id, tenant=request.tenant)
    try:
        template.name = data.name
        template.template_type = data.template_type
        template.fields_schema = data.fields_schema
        template.description = data.description
        template.updated_by = request.auth
        template.save()
        return 200, template
    except ValidationError as e:
        return 400, {"message": str(e)}


# ================= CATEGORY ENDPOINTS =================

@router.get("/categories", response=list[CategorySchema])
@paginate(LimitOffsetPagination)
def list_categories(request, is_active: bool | None = None):
    qs = Category.objects.filter(tenant=request.tenant).prefetch_related("tech_sheet_templates")
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs


@router.get("/categories/{category_id}", response=CategorySchema)
def get_category(request, category_id: UUID):
    return get_object_or_404(Category, id=category_id, tenant=request.tenant)


@router.post("/categories", response={201: CategorySchema, 400: MessageSchema})
def create_category(request, data: CategoryInputSchema):
    try:
        parent = None
        if data.parent_id:
            parent = get_object_or_404(Category, id=data.parent_id, tenant=request.tenant)

        with transaction.atomic():
            category = Category.objects.create(
                tenant=request.tenant,
                name=data.name,
                parent=parent,
                description=data.description,
                created_by=request.auth,
                updated_by=request.auth,
            )
            if data.tech_sheet_template_ids:
                templates = TechSheetTemplate.objects.filter(
                    id__in=data.tech_sheet_template_ids,
                    tenant=request.tenant
                )
                category.tech_sheet_templates.set(templates)

            return 201, category
    except ValidationError as e:
        return 400, {"message": str(e)}


@router.put("/categories/{category_id}", response={200: CategorySchema, 400: MessageSchema})
def update_category(request, category_id: UUID, data: CategoryInputSchema):
    category = get_object_or_404(Category, id=category_id, tenant=request.tenant)
    try:
        parent = None
        if data.parent_id:
            parent = get_object_or_404(Category, id=data.parent_id, tenant=request.tenant)

        with transaction.atomic():
            category.name = data.name
            category.parent = parent
            category.description = data.description
            category.updated_by = request.auth
            category.save()

            if data.tech_sheet_template_ids is not None:
                templates = TechSheetTemplate.objects.filter(
                    id__in=data.tech_sheet_template_ids,
                    tenant=request.tenant
                )
                category.tech_sheet_templates.set(templates)

            return 200, category
    except ValidationError as e:
        return 400, {"message": str(e)}


# ================= MODEL ENDPOINTS =================

@router.get("/models", response=list[ModelSchema])
@paginate(LimitOffsetPagination)
def list_models(request, is_active: bool | None = None):
    qs = Model.objects.filter(tenant=request.tenant).select_related("brand").prefetch_related("categories", "tech_sheet_templates")
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs


@router.get("/models/{model_id}", response=ModelSchema)
def get_model(request, model_id: UUID):
    return get_object_or_404(Model, id=model_id, tenant=request.tenant)


@router.post("/models", response={201: ModelSchema, 400: MessageSchema})
def create_model(request, data: ModelInputSchema):
    brand = get_object_or_404(Brand, id=data.brand_id, tenant=request.tenant)
    try:
        with transaction.atomic():
            model_obj = Model.objects.create(
                tenant=request.tenant,
                name=data.name,
                brand=brand,
                unit_of_measure=data.unit_of_measure,
                weight=data.weight,
                description=data.description,
                created_by=request.auth,
                updated_by=request.auth,
            )
            
            # Associate categories
            categories = Category.objects.filter(id__in=data.category_ids, tenant=request.tenant)
            model_obj.categories.set(categories)

            # Associate templates
            if data.tech_sheet_template_ids:
                templates = TechSheetTemplate.objects.filter(
                    id__in=data.tech_sheet_template_ids,
                    tenant=request.tenant
                )
                model_obj.tech_sheet_templates.set(templates)

            return 201, model_obj
    except ValidationError as e:
        return 400, {"message": str(e)}


@router.put("/models/{model_id}", response={200: ModelSchema, 400: MessageSchema})
def update_model(request, model_id: UUID, data: ModelInputSchema):
    model_obj = get_object_or_404(Model, id=model_id, tenant=request.tenant)
    brand = get_object_or_404(Brand, id=data.brand_id, tenant=request.tenant)
    try:
        with transaction.atomic():
            model_obj.name = data.name
            model_obj.brand = brand
            model_obj.unit_of_measure = data.unit_of_measure
            model_obj.weight = data.weight
            model_obj.description = data.description
            model_obj.updated_by = request.auth
            model_obj.save()

            categories = Category.objects.filter(id__in=data.category_ids, tenant=request.tenant)
            model_obj.categories.set(categories)

            if data.tech_sheet_template_ids is not None:
                templates = TechSheetTemplate.objects.filter(
                    id__in=data.tech_sheet_template_ids,
                    tenant=request.tenant
                )
                model_obj.tech_sheet_templates.set(templates)

            return 200, model_obj
    except ValidationError as e:
        return 400, {"message": str(e)}


# ================= ITEM ENDPOINTS =================

@router.get("/items", response=list[ItemSchema])
@paginate(LimitOffsetPagination)
def list_items(request, is_active: bool | None = None):
    qs = Item.objects.filter(tenant=request.tenant).select_related(
        "model", "model__brand"
    ).prefetch_related(
        "model__categories", "model__tech_sheet_templates"
    )
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs


@router.get("/items/{item_id}", response=ItemSchema)
def get_item(request, item_id: UUID):
    return get_object_or_404(Item, id=item_id, tenant=request.tenant)


@router.post("/items", response={201: ItemSchema, 400: MessageSchema})
def create_item(request, data: ItemInputSchema):
    model_obj = get_object_or_404(Model, id=data.model_id, tenant=request.tenant)
    try:
        item = Item.objects.create(
            tenant=request.tenant,
            model=model_obj,
            item_type=data.item_type,
            ncm=data.ncm,
            sku=data.sku or "",
            barcode=data.barcode or "",
            serial_number=data.serial_number,
            acquisition_price=data.acquisition_price,
            sale_price=data.sale_price,
            description=data.description,
            created_by=request.auth,
            updated_by=request.auth,
        )
        return 201, item
    except ValidationError as e:
        return 400, {"message": str(e)}


@router.put("/items/{item_id}", response={200: ItemSchema, 400: MessageSchema})
def update_item(request, item_id: UUID, data: ItemInputSchema):
    item = get_object_or_404(Item, id=item_id, tenant=request.tenant)
    model_obj = get_object_or_404(Model, id=data.model_id, tenant=request.tenant)
    try:
        item.model = model_obj
        item.item_type = data.item_type
        item.ncm = data.ncm
        if data.sku:
            item.sku = data.sku
        if data.barcode:
            item.barcode = data.barcode
        item.serial_number = data.serial_number
        item.acquisition_price = data.acquisition_price
        item.sale_price = data.sale_price
        item.description = data.description
        item.updated_by = request.auth
        item.save()
        return 200, item
    except ValidationError as e:
        return 400, {"message": str(e)}


# ================= BATCH ENDPOINTS =================

@router.get("/batches", response=list[BatchSchema])
@paginate(LimitOffsetPagination)
def list_batches(request, is_active: bool | None = None):
    qs = Batch.objects.filter(item__tenant=request.tenant)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs


@router.get("/batches/{batch_id}", response=BatchSchema)
def get_batch(request, batch_id: UUID):
    return get_object_or_404(Batch, id=batch_id, item__tenant=request.tenant)


@router.post("/batches", response={201: BatchSchema, 400: MessageSchema})
def create_batch(request, data: BatchInputSchema):
    item = get_object_or_404(Item, id=data.item_id, tenant=request.tenant)
    try:
        batch = Batch.objects.create(
            item=item,
            batch_code=data.batch_code,
            manufacture_date=data.manufacture_date,
            expiry_date=data.expiry_date,
            total_quantity=data.total_quantity,
            stock_quantity=data.stock_quantity,
            status=data.status,
            description=data.description,
            created_by=request.auth,
            updated_by=request.auth,
        )
        return 201, batch
    except ValidationError as e:
        return 400, {"message": str(e)}


@router.put("/batches/{batch_id}", response={200: BatchSchema, 400: MessageSchema})
def update_batch(request, batch_id: UUID, data: BatchInputSchema):
    batch = get_object_or_404(Batch, id=batch_id, item__tenant=request.tenant)
    item = get_object_or_404(Item, id=data.item_id, tenant=request.tenant)
    try:
        batch.item = item
        batch.batch_code = data.batch_code
        batch.manufacture_date = data.manufacture_date
        batch.expiry_date = data.expiry_date
        batch.total_quantity = data.total_quantity
        batch.stock_quantity = data.stock_quantity
        batch.status = data.status
        batch.description = data.description
        batch.updated_by = request.auth
        batch.save()
        return 200, batch
    except ValidationError as e:
        return 400, {"message": str(e)}
