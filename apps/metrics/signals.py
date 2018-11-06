from django.dispatch import Signal

interval_aggregated = Signal(providing_args=["left_boundary", "right_boundary"])
