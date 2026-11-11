from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.payments.api.service import FINAL_STATUSES, KhaltiError, apply_lookup_result, khalti_lookup
from apps.payments.models import Paymentlog


@require_GET
def payment_callback(request):
    """Khalti redirects the player's browser here. Nothing in the query string is trusted:
    we ask Khalti's lookup API for the real status before touching any state."""
    pidx = request.GET.get("pidx")
    if not pidx:
        return render(request, "payment/confirm.html", {"outcome": "invalid"}, status=400)

    payment_log = get_object_or_404(Paymentlog, pidx=pidx)

    if payment_log.status in FINAL_STATUSES:  # idempotent: don't even call Khalti again
        return render(request, "payment/confirm.html", {"outcome": "already_processed", "payment": payment_log})

    try:
        lookup = khalti_lookup(pidx)
    except KhaltiError:
        # Leave everything untouched so the callback can simply be retried
        return render(request, "payment/confirm.html", {"outcome": "unavailable"}, status=502)

    outcome = apply_lookup_result(payment_log.pk, lookup)
    payment_log.refresh_from_db()
    return render(request, "payment/confirm.html", {"outcome": outcome, "payment": payment_log})
