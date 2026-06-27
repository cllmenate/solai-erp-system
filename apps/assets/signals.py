from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.assets.models import Item, Batch, StockTransaction

def invalidate_dashboard_cache(tenant_id):
    if tenant_id:
        cache_key = f"dashboard_metrics_{tenant_id}"
        cache.delete(cache_key)

@receiver([post_save, post_delete], sender=Item)
def invalidate_cache_on_item_change(sender, instance, **kwargs):
    if hasattr(instance, 'tenant') and instance.tenant:
        invalidate_dashboard_cache(instance.tenant.id)

@receiver([post_save, post_delete], sender=Batch)
def invalidate_cache_on_batch_change(sender, instance, **kwargs):
    if hasattr(instance, 'item') and instance.item and hasattr(instance.item, 'tenant') and instance.item.tenant:
        invalidate_dashboard_cache(instance.item.tenant.id)

@receiver([post_save, post_delete], sender=StockTransaction)
def invalidate_cache_on_transaction_change(sender, instance, **kwargs):
    if hasattr(instance, 'tenant') and instance.tenant:
        invalidate_dashboard_cache(instance.tenant.id)
