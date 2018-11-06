# coding=UTF8
import functools


def disabled_hstore_fields(f):
    """Helper decorator for HStoreSerializer."""

    @functools.wraps(f)
    def outer(self, *args, **kwargs):
        """
        temporarily remove hstore virtual fields otherwise DRF considers them many2many
        """
        model = self.Meta.model
        meta = self.Meta.model._meta
        original_private_fields = list(meta.private_fields)  # copy

        if hasattr(model, '_hstore_virtual_fields'):
            # remove hstore virtual fields from meta
            for field in model._hstore_virtual_fields.values():
                meta.private_fields.remove(field)

        try:
            return f(self, *args, **kwargs)
        finally:
            if hasattr(model, '_hstore_virtual_fields'):
                # restore original virtual fields
                meta.private_fields = original_private_fields
    return outer
