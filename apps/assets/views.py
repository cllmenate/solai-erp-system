import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.core.cache import cache
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.assets.models import Batch, Brand, Category, Item, Model, StockTransaction
from apps.core.decorators import tenant_permission_required


@login_required
@tenant_permission_required("assets.view_item")
def item_list_view(request):
    """
    Renders list of items for the active tenant.
    Supports advanced searching by SKU, barcode, NCM, category, brand, and item_type.
    """
    search_query = request.GET.get("search", "")
    item_type = request.GET.get("type", "")
    brand_id = request.GET.get("brand", "")
    category_id = request.GET.get("category", "")
    ncm_query = request.GET.get("ncm", "")
    min_sale_price = request.GET.get("min_sale_price", "")
    max_sale_price = request.GET.get("max_sale_price", "")
    min_acquisition_price = request.GET.get("min_acquisition_price", "")
    max_acquisition_price = request.GET.get("max_acquisition_price", "")

    queryset = Item.objects.filter(tenant=request.tenant, is_active=True).select_related(
        "model", "model__brand"
    ).prefetch_related(
        "model__categories"
    )

    needs_distinct = False

    if search_query:
        queryset = queryset.filter(
            Q(sku__icontains=search_query) |
            Q(barcode__icontains=search_query) |
            Q(ncm__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(model__name__icontains=search_query) |
            Q(model__brand__name__icontains=search_query) |
            Q(model__categories__name__icontains=search_query)
        )
        needs_distinct = True

    if item_type:
        queryset = queryset.filter(item_type=item_type)

    if ncm_query:
        queryset = queryset.filter(ncm__icontains=ncm_query)

    if brand_id:
        queryset = queryset.filter(model__brand_id=brand_id)

    if category_id:
        queryset = queryset.filter(model__categories__id=category_id)
        needs_distinct = True

    if min_sale_price:
        queryset = queryset.filter(sale_price__gte=min_sale_price)

    if max_sale_price:
        queryset = queryset.filter(sale_price__lte=max_sale_price)

    if min_acquisition_price:
        queryset = queryset.filter(acquisition_price__gte=min_acquisition_price)

    if max_acquisition_price:
        queryset = queryset.filter(acquisition_price__lte=max_acquisition_price)

    if needs_distinct:
        queryset = queryset.distinct()

    queryset = queryset.order_by("-created_at")

    # Pagination: 20 items per page
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    brands = Brand.objects.filter(tenant=request.tenant, is_active=True).order_by("name")
    categories = Category.objects.filter(tenant=request.tenant, is_active=True).order_by("name")

    context = {
        "page_obj": page_obj,
        "items": page_obj.object_list,
        "search_query": search_query,
        "item_type": item_type,
        "brand_id": brand_id,
        "category_id": category_id,
        "ncm_query": ncm_query,
        "min_sale_price": min_sale_price,
        "max_sale_price": max_sale_price,
        "min_acquisition_price": min_acquisition_price,
        "max_acquisition_price": max_acquisition_price,
        "brands": brands,
        "categories": categories,
    }
    return render(request, "assets/item_list.html", context)


@login_required
@tenant_permission_required("assets.view_item")
def item_detail_view(request, pk):
    """
    Renders item details with its batches and audit log.
    """
    item = get_object_or_404(Item, id=pk, tenant=request.tenant)
    batches = item.batches.all().order_by("expiry_date") # FIFO view
    
    # Calculate inherited nutritional specs
    nutritional_specs = {}
    for template in item.model.all_tech_sheet_templates:
        if template.template_type == "nutritional":
            nutritional_specs.update(template.fields_schema)

    # Calculate audit history using simple history
    history_records = item.history.all().order_by("-history_date")
    audit_history = []
    
    for i in range(len(history_records)):
        new_record = history_records[i]
        if i + 1 < len(history_records):
            old_record = history_records[i+1]
            delta = new_record.diff_against(old_record)
            fields_changed = []
            for change in delta.changes:
                fields_changed.append({
                    "field": change.field,
                    "old": change.old,
                    "new": change.new
                })
            audit_history.append({
                "date": new_record.history_date,
                "user": new_record.history_user,
                "type": "update",
                "type_display": "Atualização",
                "fields": fields_changed
            })
        else:
            audit_history.append({
                "date": new_record.history_date,
                "user": new_record.history_user,
                "type": "create",
                "type_display": "Criação",
                "fields": []
            })

    context = {
        "item": item,
        "batches": batches,
        "nutritional_specs": nutritional_specs,
        "audit_history": audit_history,
    }
    return render(request, "assets/item_detail.html", context)


@login_required
@tenant_permission_required("assets.add_item")
def item_create_view(request):
    """
    Handles rendering and processing item creation.
    """
    brands = Brand.objects.filter(tenant=request.tenant, is_active=True)
    categories = Category.objects.filter(tenant=request.tenant, is_active=True)
    models_qs = Model.objects.filter(tenant=request.tenant, is_active=True)

    if request.method == "POST":
        model_id = request.POST.get("model")
        item_type = request.POST.get("item_type")
        name = request.POST.get("name")
        ncm = request.POST.get("ncm")
        sku = request.POST.get("sku")
        barcode = request.POST.get("barcode")
        serial_number = request.POST.get("serial_number")
        acquisition_price = request.POST.get("acquisition_price", "0")
        sale_price = request.POST.get("sale_price", "0")
        minimum_stock = request.POST.get("minimum_stock", "0")
        description = request.POST.get("description")

        model_obj = get_object_or_404(Model, id=model_id, tenant=request.tenant)

        try:
            with transaction.atomic():
                item = Item.objects.create(
                    tenant=request.tenant,
                    name=name,
                    model=model_obj,
                    item_type=item_type,
                    ncm=ncm,
                    sku=sku,
                    barcode=barcode,
                    serial_number=serial_number,
                    acquisition_price=acquisition_price,
                    sale_price=sale_price,
                    minimum_stock=minimum_stock,
                    description=description,
                    created_by=request.user,
                    updated_by=request.user,
                )
                messages.success(request, f"Item '{item.name}' criado com sucesso.")
                return redirect("item_detail", pk=item.id)
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao criar item: {str(e)}")

    context = {
        "brands": brands,
        "categories": categories,
        "models": models_qs,
        "item_types": Item.ITEM_TYPES,
    }
    return render(request, "assets/item_form.html", context)


@login_required
@tenant_permission_required("assets.change_item")
def item_update_view(request, pk):
    """
    Handles editing an existing item.
    """
    item = get_object_or_404(Item, id=pk, tenant=request.tenant)
    models_qs = Model.objects.filter(tenant=request.tenant, is_active=True)

    if request.method == "POST":
        model_id = request.POST.get("model")
        item_type = request.POST.get("item_type")
        name = request.POST.get("name")
        ncm = request.POST.get("ncm")
        sku = request.POST.get("sku")
        barcode = request.POST.get("barcode")
        serial_number = request.POST.get("serial_number")
        acquisition_price = request.POST.get("acquisition_price", "0")
        sale_price = request.POST.get("sale_price", "0")
        minimum_stock = request.POST.get("minimum_stock", "0")
        description = request.POST.get("description")

        model_obj = get_object_or_404(Model, id=model_id, tenant=request.tenant)

        try:
            with transaction.atomic():
                item.name = name
                item.model = model_obj
                item.item_type = item_type
                item.ncm = ncm
                if sku:
                    item.sku = sku
                if barcode:
                    item.barcode = barcode
                item.serial_number = serial_number
                item.acquisition_price = acquisition_price
                item.sale_price = sale_price
                item.minimum_stock = minimum_stock
                item.description = description
                item.updated_by = request.user
                item.save()
                messages.success(request, f"Item '{item.name}' atualizado com sucesso.")
                return redirect("item_detail", pk=item.id)
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao atualizar item: {str(e)}")

    context = {
        "item": item,
        "models": models_qs,
        "item_types": Item.ITEM_TYPES,
    }
    return render(request, "assets/item_form.html", context)


@login_required
@tenant_permission_required("assets.delete_item")
def item_delete_view(request, pk):
    """
    Deactivates an item.
    """
    item = get_object_or_404(Item, id=pk, tenant=request.tenant)
    item.is_active = False
    item.save()
    messages.success(request, f"Item '{item.name}' desativado com sucesso.")
    return redirect("item_list")


# ================= BRAND CRUD VIEWS =================

@login_required
@tenant_permission_required("assets.view_brand")
def brand_list_view(request):
    search_query = request.GET.get("search", "")
    brands = Brand.objects.filter(tenant=request.tenant, is_active=True)
    if search_query:
        brands = brands.filter(Q(name__icontains=search_query))
    brands = brands.order_by("-created_at")
    return render(request, "assets/brand_list.html", {"brands": brands, "search_query": search_query})


@login_required
@tenant_permission_required("assets.add_brand")
def brand_create_view(request):
    if request.method == "POST":
        name = request.POST.get("name")
        website = request.POST.get("website")
        description = request.POST.get("description")
        try:
            brand = Brand.objects.create(
                tenant=request.tenant,
                name=name,
                website=website or None,
                description=description,
                created_by=request.user,
                updated_by=request.user,
            )
            messages.success(request, f"Marca '{brand.name}' criada com sucesso.")
            return redirect("brand_list")
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao criar marca: {str(e)}")

    return render(request, "assets/brand_form.html")


@login_required
@tenant_permission_required("assets.change_brand")
def brand_update_view(request, pk):
    brand = get_object_or_404(Brand, id=pk, tenant=request.tenant)
    if request.method == "POST":
        brand.name = request.POST.get("name")
        brand.website = request.POST.get("website") or None
        brand.description = request.POST.get("description")
        brand.updated_by = request.user
        try:
            brand.save()
            messages.success(request, f"Marca '{brand.name}' atualizada com sucesso.")
            return redirect("brand_list")
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao atualizar marca: {str(e)}")

    return render(request, "assets/brand_form.html", {"brand": brand})


@login_required
@tenant_permission_required("assets.delete_brand")
def brand_delete_view(request, pk):
    brand = get_object_or_404(Brand, id=pk, tenant=request.tenant)
    brand.is_active = False
    brand.save()
    messages.success(request, f"Marca '{brand.name}' desativada com sucesso.")
    return redirect("brand_list")


# ================= CATEGORY CRUD VIEWS =================

@login_required
@tenant_permission_required("assets.view_category")
def category_list_view(request):
    search_query = request.GET.get("search", "")
    categories = Category.objects.filter(tenant=request.tenant, is_active=True)
    if search_query:
        categories = categories.filter(Q(name__icontains=search_query))
    categories = categories.order_by("-created_at")
    return render(request, "assets/category_list.html", {"categories": categories, "search_query": search_query})


@login_required
@tenant_permission_required("assets.add_category")
def category_create_view(request):
    categories = Category.objects.filter(tenant=request.tenant, is_active=True)
    if request.method == "POST":
        name = request.POST.get("name")
        parent_id = request.POST.get("parent")
        description = request.POST.get("description")
        
        parent = None
        if parent_id:
            parent = get_object_or_404(Category, id=parent_id, tenant=request.tenant)
            
        try:
            category = Category.objects.create(
                tenant=request.tenant,
                name=name,
                parent=parent,
                description=description,
                created_by=request.user,
                updated_by=request.user,
            )
            messages.success(request, f"Categoria '{category.name}' criada com sucesso.")
            return redirect("category_list")
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao criar categoria: {str(e)}")

    return render(request, "assets/category_form.html", {"categories": categories})


@login_required
@tenant_permission_required("assets.change_category")
def category_update_view(request, pk):
    category = get_object_or_404(Category, id=pk, tenant=request.tenant)
    categories = Category.objects.filter(tenant=request.tenant, is_active=True).exclude(id=category.id)
    if request.method == "POST":
        category.name = request.POST.get("name")
        parent_id = request.POST.get("parent")
        category.description = request.POST.get("description")
        category.updated_by = request.user
        
        if parent_id:
            category.parent = get_object_or_404(Category, id=parent_id, tenant=request.tenant)
        else:
            category.parent = None
            
        try:
            category.save()
            messages.success(request, f"Categoria '{category.name}' atualizada com sucesso.")
            return redirect("category_list")
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao atualizar categoria: {str(e)}")

    return render(request, "assets/category_form.html", {"category": category, "categories": categories})


@login_required
@tenant_permission_required("assets.delete_category")
def category_delete_view(request, pk):
    category = get_object_or_404(Category, id=pk, tenant=request.tenant)
    category.is_active = False
    category.save()
    messages.success(request, f"Categoria '{category.name}' desativada com sucesso.")
    return redirect("category_list")


# ================= MODEL CRUD VIEWS =================

@login_required
@tenant_permission_required("assets.view_model")
def model_list_view(request):
    search_query = request.GET.get("search", "")
    category_id = request.GET.get("category", "")
    models_qs = Model.objects.filter(tenant=request.tenant, is_active=True).select_related("brand")
    
    if search_query:
        models_qs = models_qs.filter(Q(name__icontains=search_query) | Q(brand__name__icontains=search_query))
        
    if category_id:
        models_qs = models_qs.filter(categories__id=category_id).distinct()
        
    models_qs = models_qs.order_by("-created_at")
    categories = Category.objects.filter(tenant=request.tenant, is_active=True).order_by("name")
    
    context = {
        "models": models_qs,
        "search_query": search_query,
        "category_id": category_id,
        "categories": categories,
    }
    return render(request, "assets/model_list.html", context)


@login_required
@tenant_permission_required("assets.add_model")
def model_create_view(request):
    brands = Brand.objects.filter(tenant=request.tenant, is_active=True)
    categories = Category.objects.filter(tenant=request.tenant, is_active=True)
    if request.method == "POST":
        name = request.POST.get("name")
        brand_id = request.POST.get("brand")
        category_ids = request.POST.getlist("categories")
        unit_of_measure = request.POST.get("unit_of_measure")
        weight = request.POST.get("weight")
        description = request.POST.get("description")
        
        brand = get_object_or_404(Brand, id=brand_id, tenant=request.tenant)
        
        try:
            with transaction.atomic():
                model_obj = Model.objects.create(
                    tenant=request.tenant,
                    name=name,
                    brand=brand,
                    unit_of_measure=unit_of_measure,
                    weight=weight or None,
                    description=description,
                    created_by=request.user,
                    updated_by=request.user,
                )
                if category_ids:
                    cats = Category.objects.filter(id__in=category_ids, tenant=request.tenant)
                    model_obj.categories.set(cats)
                    
            messages.success(request, f"Modelo '{model_obj.name}' criado com sucesso.")
            return redirect("model_list")
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao criar modelo: {str(e)}")

    return render(request, "assets/model_form.html", {"brands": brands, "categories": categories})


@login_required
@tenant_permission_required("assets.change_model")
def model_update_view(request, pk):
    model_obj = get_object_or_404(Model, id=pk, tenant=request.tenant)
    brands = Brand.objects.filter(tenant=request.tenant, is_active=True)
    categories = Category.objects.filter(tenant=request.tenant, is_active=True)
    selected_category_ids = model_obj.categories.values_list("id", flat=True)
    
    if request.method == "POST":
        brand_id = request.POST.get("brand")
        category_ids = request.POST.getlist("categories")
        
        model_obj.name = request.POST.get("name")
        model_obj.brand = get_object_or_404(Brand, id=brand_id, tenant=request.tenant)
        model_obj.unit_of_measure = request.POST.get("unit_of_measure")
        model_obj.weight = request.POST.get("weight") or None
        model_obj.description = request.POST.get("description")
        model_obj.updated_by = request.user
        
        try:
            with transaction.atomic():
                model_obj.save()
                if category_ids:
                    cats = Category.objects.filter(id__in=category_ids, tenant=request.tenant)
                    model_obj.categories.set(cats)
                else:
                    model_obj.categories.clear()
            messages.success(request, f"Modelo '{model_obj.name}' atualizado com sucesso.")
            return redirect("model_list")
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao atualizar modelo: {str(e)}")

    return render(request, "assets/model_form.html", {
        "model": model_obj,
        "brands": brands,
        "categories": categories,
        "selected_category_ids": selected_category_ids,
    })


@login_required
@tenant_permission_required("assets.delete_model")
def model_delete_view(request, pk):
    model_obj = get_object_or_404(Model, id=pk, tenant=request.tenant)
    model_obj.is_active = False
    model_obj.save()
    messages.success(request, f"Modelo '{model_obj.name}' desativado com sucesso.")
    return redirect("model_list")


# ================= BATCH CRUD VIEWS =================

@login_required
@tenant_permission_required("assets.view_batch")
def batch_list_view(request):
    search_query = request.GET.get("search", "")
    status_query = request.GET.get("status", "")
    expiry_min = request.GET.get("expiry_min", "")
    expiry_max = request.GET.get("expiry_max", "")
    
    batches = Batch.objects.filter(item__tenant=request.tenant, is_active=True).select_related("item", "item__model")
    
    if search_query:
        batches = batches.filter(Q(batch_code__icontains=search_query) | Q(item__name__icontains=search_query))
        
    if status_query:
        batches = batches.filter(status=status_query)
        
    if expiry_min:
        batches = batches.filter(expiry_date__gte=expiry_min)
        
    if expiry_max:
        batches = batches.filter(expiry_date__lte=expiry_max)
        
    batches = batches.order_by("-created_at")
    
    context = {
        "batches": batches,
        "search_query": search_query,
        "status_query": status_query,
        "expiry_min": expiry_min,
        "expiry_max": expiry_max,
    }
    return render(request, "assets/batch_list.html", context)


@login_required
@tenant_permission_required("assets.view_batch")
def batch_detail_view(request, pk):
    batch = get_object_or_404(Batch, id=pk, item__tenant=request.tenant)
    audit_history = []
    history_records = batch.history.all().order_by("-history_date")
    for i in range(len(history_records)):
        new_record = history_records[i]
        if i + 1 < len(history_records):
            old_record = history_records[i+1]
            delta = new_record.diff_against(old_record)
            fields_changed = []
            for change in delta.changes:
                fields_changed.append({
                    "field": change.field,
                    "old": change.old,
                    "new": change.new
                })
            audit_history.append({
                "date": new_record.history_date,
                "user": new_record.history_user,
                "type": "update",
                "type_display": "Atualização",
                "fields": fields_changed
            })
        else:
            audit_history.append({
                "date": new_record.history_date,
                "user": new_record.history_user,
                "type": "create",
                "type_display": "Criação",
                "fields": []
            })
    transactions = batch.transactions.all().order_by("-created_at")
    context = {
        "batch": batch,
        "audit_history": audit_history,
        "transactions": transactions,
    }
    return render(request, "assets/batch_detail.html", context)


@login_required
@tenant_permission_required("assets.add_batch")
def batch_create_view(request):
    items = Item.objects.filter(tenant=request.tenant, is_active=True).select_related("model")
    if request.method == "POST":
        item_id = request.POST.get("item")
        batch_code = request.POST.get("batch_code")
        manufacture_date = request.POST.get("manufacture_date")
        expiry_date = request.POST.get("expiry_date")
        total_quantity = request.POST.get("total_quantity")
        stock_quantity = request.POST.get("stock_quantity")
        status = request.POST.get("status", "active")
        description = request.POST.get("description")
        
        item = get_object_or_404(Item, id=item_id, tenant=request.tenant)
        
        try:
            batch = Batch.objects.create(
                item=item,
                batch_code=batch_code,
                manufacture_date=manufacture_date,
                expiry_date=expiry_date,
                total_quantity=total_quantity,
                stock_quantity=stock_quantity,
                status=status,
                description=description,
                created_by=request.user,
                updated_by=request.user,
            )
            messages.success(request, f"Lote '{batch.batch_code}' criado com sucesso para o item '{item.name}'.")
            return redirect("batch_list")
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao criar lote: {str(e)}")

    return render(request, "assets/batch_form.html", {"items": items, "status_choices": Batch.STATUS_CHOICES})


@login_required
@tenant_permission_required("assets.change_batch")
def batch_update_view(request, pk):
    batch = get_object_or_404(Batch, id=pk, item__tenant=request.tenant)
    items = Item.objects.filter(tenant=request.tenant, is_active=True).select_related("model")
    if request.method == "POST":
        item_id = request.POST.get("item")
        
        batch.item = get_object_or_404(Item, id=item_id, tenant=request.tenant)
        batch.batch_code = request.POST.get("batch_code")
        batch.manufacture_date = request.POST.get("manufacture_date")
        batch.expiry_date = request.POST.get("expiry_date")
        batch.total_quantity = request.POST.get("total_quantity")
        batch.stock_quantity = request.POST.get("stock_quantity")
        batch.status = request.POST.get("status")
        batch.description = request.POST.get("description")
        batch.updated_by = request.user
        
        try:
            batch.save()
            messages.success(request, f"Lote '{batch.batch_code}' atualizado com sucesso.")
            return redirect("batch_list")
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao atualizar lote: {str(e)}")

    # Calculate audit history using simple history for batch
    history_records = batch.history.all().order_by("-history_date")
    audit_history = []
    
    for i in range(len(history_records)):
        new_record = history_records[i]
        if i + 1 < len(history_records):
            old_record = history_records[i+1]
            delta = new_record.diff_against(old_record)
            fields_changed = []
            for change in delta.changes:
                fields_changed.append({
                    "field": change.field,
                    "old": change.old,
                    "new": change.new
                })
            audit_history.append({
                "date": new_record.history_date,
                "user": new_record.history_user,
                "type": "update",
                "type_display": "Atualização",
                "fields": fields_changed
            })
        else:
            audit_history.append({
                "date": new_record.history_date,
                "user": new_record.history_user,
                "type": "create",
                "type_display": "Criação",
                "fields": []
            })

    return render(
        request, 
        "assets/batch_form.html", 
        {
            "batch": batch, 
            "items": items, 
            "status_choices": Batch.STATUS_CHOICES,
            "audit_history": audit_history
        }
    )


@login_required
@tenant_permission_required("assets.delete_batch")
def batch_delete_view(request, pk):
    batch = get_object_or_404(Batch, id=pk, item__tenant=request.tenant)
    batch.is_active = False
    batch.save()
# ================= BATCH CRUD VIEWS =================

@login_required
@tenant_permission_required("assets.view_batch")
def batch_list_view(request):
    search_query = request.GET.get("search", "")
    status_query = request.GET.get("status", "")
    expiry_min = request.GET.get("expiry_min", "")
    expiry_max = request.GET.get("expiry_max", "")
    
    batches = Batch.objects.filter(item__tenant=request.tenant, is_active=True).select_related("item", "item__model")
    
    if search_query:
        batches = batches.filter(Q(batch_code__icontains=search_query) | Q(item__name__icontains=search_query))
        
    if status_query:
        batches = batches.filter(status=status_query)
        
    if expiry_min:
        batches = batches.filter(expiry_date__gte=expiry_min)
        
    if expiry_max:
        batches = batches.filter(expiry_date__lte=expiry_max)
        
    batches = batches.order_by("-created_at")
    
    context = {
        "batches": batches,
        "search_query": search_query,
        "status_query": status_query,
        "expiry_min": expiry_min,
        "expiry_max": expiry_max,
    }
    return render(request, "assets/batch_list.html", context)


@login_required
@tenant_permission_required("assets.view_batch")
def batch_detail_view(request, pk):
    batch = get_object_or_404(Batch, id=pk, item__tenant=request.tenant)
    audit_history = []
    history_records = batch.history.all().order_by("-history_date")
    for i in range(len(history_records)):
        new_record = history_records[i]
        if i + 1 < len(history_records):
            old_record = history_records[i+1]
            delta = new_record.diff_against(old_record)
            fields_changed = []
            for change in delta.changes:
                fields_changed.append({
                    "field": change.field,
                    "old": change.old,
                    "new": change.new
                })
            audit_history.append({
                "date": new_record.history_date,
                "user": new_record.history_user,
                "type": "update",
                "type_display": "Atualização",
                "fields": fields_changed
            })
        else:
            audit_history.append({
                "date": new_record.history_date,
                "user": new_record.history_user,
                "type": "create",
                "type_display": "Criação",
                "fields": []
            })
    transactions = batch.transactions.all().order_by("-created_at")
    context = {
        "batch": batch,
        "audit_history": audit_history,
        "transactions": transactions,
    }
    return render(request, "assets/batch_detail.html", context)


@login_required
@tenant_permission_required("assets.add_batch")
def batch_create_view(request):
    items = Item.objects.filter(tenant=request.tenant, is_active=True).select_related("model")
    if request.method == "POST":
        item_id = request.POST.get("item")
        batch_code = request.POST.get("batch_code")
        manufacture_date = request.POST.get("manufacture_date")
        expiry_date = request.POST.get("expiry_date")
        total_quantity = request.POST.get("total_quantity")
        stock_quantity = request.POST.get("stock_quantity")
        status = request.POST.get("status", "active")
        description = request.POST.get("description")
        
        item = get_object_or_404(Item, id=item_id, tenant=request.tenant)
        
        try:
            batch = Batch.objects.create(
                item=item,
                batch_code=batch_code,
                manufacture_date=manufacture_date,
                expiry_date=expiry_date,
                total_quantity=total_quantity,
                stock_quantity=stock_quantity,
                status=status,
                description=description,
                created_by=request.user,
                updated_by=request.user,
            )
            messages.success(request, f"Lote '{batch.batch_code}' criado com sucesso para o item '{item.name}'.")
            return redirect("batch_list")
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao criar lote: {str(e)}")

    return render(request, "assets/batch_form.html", {"items": items, "status_choices": Batch.STATUS_CHOICES})


@login_required
@tenant_permission_required("assets.change_batch")
def batch_update_view(request, pk):
    batch = get_object_or_404(Batch, id=pk, item__tenant=request.tenant)
    items = Item.objects.filter(tenant=request.tenant, is_active=True).select_related("model")
    if request.method == "POST":
        item_id = request.POST.get("item")
        
        batch.item = get_object_or_404(Item, id=item_id, tenant=request.tenant)
        batch.batch_code = request.POST.get("batch_code")
        batch.manufacture_date = request.POST.get("manufacture_date")
        batch.expiry_date = request.POST.get("expiry_date")
        batch.total_quantity = request.POST.get("total_quantity")
        batch.stock_quantity = request.POST.get("stock_quantity")
        batch.status = request.POST.get("status")
        batch.description = request.POST.get("description")
        batch.updated_by = request.user
        
        try:
            batch.save()
            messages.success(request, f"Lote '{batch.batch_code}' atualizado com sucesso.")
            return redirect("batch_list")
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao atualizar lote: {str(e)}")

    # Calculate audit history using simple history for batch
    history_records = batch.history.all().order_by("-history_date")
    audit_history = []
    
    for i in range(len(history_records)):
        new_record = history_records[i]
        if i + 1 < len(history_records):
            old_record = history_records[i+1]
            delta = new_record.diff_against(old_record)
            fields_changed = []
            for change in delta.changes:
                fields_changed.append({
                    "field": change.field,
                    "old": change.old,
                    "new": change.new
                })
            audit_history.append({
                "date": new_record.history_date,
                "user": new_record.history_user,
                "type": "update",
                "type_display": "Atualização",
                "fields": fields_changed
            })
        else:
            audit_history.append({
                "date": new_record.history_date,
                "user": new_record.history_user,
                "type": "create",
                "type_display": "Criação",
                "fields": []
            })

    return render(
        request, 
        "assets/batch_form.html", 
        {
            "batch": batch, 
            "items": items, 
            "status_choices": Batch.STATUS_CHOICES,
            "audit_history": audit_history
        }
    )


@login_required
@tenant_permission_required("assets.delete_batch")
def batch_delete_view(request, pk):
    batch = get_object_or_404(Batch, id=pk, item__tenant=request.tenant)
    batch.is_active = False
    batch.save()
    messages.success(request, f"Lote '{batch.batch_code}' desativado com sucesso.")
    return redirect("batch_list")


@login_required
@tenant_permission_required("assets.view_item")
def stock_dashboard_view(request):
    """
    Renders consolidated Stock/Assets Dashboard.
    Uses Redis cache for real-time data efficiency.
    """
    tenant_id = request.tenant.id
    cache_key = f"dashboard_metrics_{tenant_id}"
    
    context = cache.get(cache_key)
    
    if not context:
        # 1. Total distinct active items
        total_items = Item.objects.filter(tenant=request.tenant, is_active=True).count()

        # 2. Total active stock quantity
        total_qty = Batch.objects.filter(
            item__tenant=request.tenant,
            item__is_active=True,
            is_active=True,
            status="active"
        ).aggregate(total=Sum("stock_quantity"))["total"] or 0

        # 3. Total value of inventory
        batches = Batch.objects.filter(
            item__tenant=request.tenant,
            item__is_active=True,
            is_active=True,
            status="active"
        ).select_related("item")
        total_value = sum(b.stock_quantity * b.item.acquisition_price for b in batches)

        # 4. Expiration warnings (expired or expiring in next 30 days)
        now_date = timezone.now().date()
        thirty_days_hence = now_date + datetime.timedelta(days=30)
        
        expiring_batches = Batch.objects.filter(
            item__tenant=request.tenant,
            item__is_active=True,
            is_active=True,
            status="active",
            expiry_date__lte=thirty_days_hence
        ).select_related("item", "item__model").order_by("expiry_date")

        expired_count = expiring_batches.filter(expiry_date__lt=now_date).count()
        expiring_soon_count = expiring_batches.filter(expiry_date__gte=now_date).count()
        total_expiration_alerts = expiring_batches.count()

        # 5. Low stock warnings (total stock quantity < minimum_stock)
        items = Item.objects.filter(
            tenant=request.tenant,
            is_active=True
        ).annotate(
            current_stock=Sum("batches__stock_quantity", filter=Q(batches__is_active=True, batches__status="active"))
        ).select_related("model")

        low_stock_items = []
        for item in items:
            curr_stock = item.current_stock or 0
            if curr_stock < item.minimum_stock:
                low_stock_items.append({
                    "item": item,
                    "current_stock": curr_stock,
                    "minimum_stock": item.minimum_stock
                })
        low_stock_count = len(low_stock_items)

        # 6. Consolidated stock by Category
        categories = Category.objects.filter(tenant=request.tenant, is_active=True)
        category_data = []
        for cat in categories:
            cat_items = Item.objects.filter(
                tenant=request.tenant,
                is_active=True,
                model__categories=cat
            ).annotate(
                qty=Sum("batches__stock_quantity", filter=Q(batches__is_active=True, batches__status="active"))
            )
            qty_sum = sum(i.qty or 0 for i in cat_items)
            if qty_sum > 0 or cat_items.exists():
                category_data.append({
                    "category": cat,
                    "total_quantity": qty_sum,
                    "items_count": cat_items.count()
                })

        context = {
            "total_items": total_items,
            "total_qty": total_qty,
            "total_value": total_value,
            "expired_count": expired_count,
            "expiring_soon_count": expiring_soon_count,
            "total_expiration_alerts": total_expiration_alerts,
            "expiring_batches": list(expiring_batches),
            "low_stock_items": low_stock_items,
            "low_stock_count": low_stock_count,
            "category_data": category_data,
            "items": list(items),
        }
        
        cache.set(cache_key, context, timeout=900)

    return render(request, "assets/stock_dashboard.html", context)


@tenant_permission_required("assets.view_brand")
def brand_detail_view(request, pk):
    brand = get_object_or_404(Brand, id=pk, tenant=request.tenant)
    audit_history = []
    history_records = brand.history.all().order_by("-history_date")
    for record in history_records:
        changes = []
        if record.prev_record:
            delta = record.diff_against(record.prev_record)
            for change in delta.changes:
                changes.append({
                    "field": change.field,
                    "old": change.old,
                    "new": change.new
                })
        audit_history.append({
            "date": record.history_date,
            "user": record.history_user,
            "type": "create" if record.history_type == "+" else "update",
            "fields": changes
        })
    context = {
        "brand": brand,
        "audit_history": audit_history
    }
    return render(request, "assets/brand_detail.html", context)

@tenant_permission_required("assets.view_category")
def category_detail_view(request, pk):
    category = get_object_or_404(Category, id=pk, tenant=request.tenant)
    audit_history = []
    history_records = category.history.all().order_by("-history_date")
    for record in history_records:
        changes = []
        if record.prev_record:
            delta = record.diff_against(record.prev_record)
            for change in delta.changes:
                changes.append({
                    "field": change.field,
                    "old": change.old,
                    "new": change.new
                })
        audit_history.append({
            "date": record.history_date,
            "user": record.history_user,
            "type": "create" if record.history_type == "+" else "update",
            "fields": changes
        })
    context = {
        "category": category,
        "audit_history": audit_history
    }
    return render(request, "assets/category_detail.html", context)

@tenant_permission_required("assets.view_model")
def model_detail_view(request, pk):
    model_obj = get_object_or_404(Model, id=pk, tenant=request.tenant)
    audit_history = []
    history_records = model_obj.history.all().order_by("-history_date")
    for record in history_records:
        changes = []
        if record.prev_record:
            delta = record.diff_against(record.prev_record)
            for change in delta.changes:
                changes.append({
                    "field": change.field,
                    "old": change.old,
                    "new": change.new
                })
        audit_history.append({
            "date": record.history_date,
            "user": record.history_user,
            "type": "create" if record.history_type == "+" else "update",
            "fields": changes
        })
    context = {
        "model": model_obj,
        "audit_history": audit_history
    }
    return render(request, "assets/model_detail.html", context)

@tenant_permission_required("assets.view_techsheettemplate")
def tech_sheet_template_detail_view(request, pk):
    from apps.assets.models import TechSheetTemplate
    template = get_object_or_404(TechSheetTemplate, id=pk, tenant=request.tenant)
    audit_history = []
    history_records = template.history.all().order_by("-history_date")
    for record in history_records:
        changes = []
        if record.prev_record:
            delta = record.diff_against(record.prev_record)
            for change in delta.changes:
                changes.append({
                    "field": change.field,
                    "old": change.old,
                    "new": change.new
                })
        audit_history.append({
            "date": record.history_date,
            "user": record.history_user,
            "type": "create" if record.history_type == "+" else "update",
            "fields": changes
        })
    context = {
        "template": template,
        "audit_history": audit_history
    }
    return render(request, "assets/tech_sheet_template_detail.html", context)


@login_required
@tenant_permission_required("assets.view_batch")
def stock_transaction_list_view(request):
    """
    List all stock transactions for the active tenant.
    """
    search_query = request.GET.get("search", "")
    queryset = StockTransaction.objects.filter(tenant=request.tenant).select_related(
        "batch", "batch__item", "created_by"
    )

    if search_query:
        queryset = queryset.filter(
            Q(name__icontains=search_query) |
            Q(batch__batch_code__icontains=search_query) |
            Q(batch__item__name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Pagination: 20 per page
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "transactions": page_obj.object_list,
        "search_query": search_query,
    }
    return render(request, "assets/stock_transaction_list.html", context)


@login_required
@tenant_permission_required("assets.add_batch")
def stock_transaction_create_view(request):
    """
    Create a new manual stock transaction (input or output).
    """
    batches = Batch.objects.filter(item__tenant=request.tenant, is_active=True).select_related("item")
    
    if request.method == "POST":
        batch_id = request.POST.get("batch")
        transaction_type = request.POST.get("transaction_type")
        quantity = request.POST.get("quantity")
        description = request.POST.get("description")
        
        batch = get_object_or_404(Batch, id=batch_id, item__tenant=request.tenant)
        
        try:
            with transaction.atomic():
                tx = StockTransaction.objects.create(
                    tenant=request.tenant,
                    batch=batch,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    description=description,
                    created_by=request.user,
                    updated_by=request.user,
                )
                messages.success(request, f"Movimentação registrada com sucesso: {tx.name}.")
                return redirect("stock_transaction_list")
        except ValidationError as e:
            messages.error(request, f"Erro de validação: {e.messages}")
        except Exception as e:
            messages.error(request, f"Erro ao registrar movimentação: {str(e)}")

    context = {
        "batches": batches,
        "transaction_types": StockTransaction.TRANSACTION_TYPES,
        "batch_id": request.GET.get("batch_id", "")
    }
    return render(request, "assets/stock_transaction_form.html", context)
