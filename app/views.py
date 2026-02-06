#from django.shortcuts import render
from django.http import HttpResponse

from django.shortcuts import render, get_object_or_404
from django.http import Http404
from django.db.models import Q
from collections import defaultdict

from .models import Customer, Material

def home(request):
    return HttpResponse("Welcome to the Home Page!")


def customer_list(request):
    q = request.GET.get("q", "").strip()

    customers_qs = Customer.objects.all().order_by("customer_name")

    if q:
        customers_qs = customers_qs.filter(
            Q(customer_name__icontains=q) |
            Q(tep_code__icontains=q) |
            Q(part_code__icontains=q)
        )

    grouped = {}
    for cust in customers_qs:
        name = cust.customer_name
        tmap = grouped.setdefault(name, {})
        tep_field = (cust.tep_code or "").strip()
        part_field = (cust.part_code or "").strip()
        if not tep_field:
            continue
        tep_codes = [s.strip() for s in tep_field.split(',') if s.strip()]
        part_codes = [s.strip() for s in part_field.split(',') if s.strip()]
        for tep in tep_codes:
            entry = tmap.setdefault(tep, {"part_codes": set(), "materials_count": 0})
            for pc in part_codes:
                entry["part_codes"].add(pc)
            try:
                entry["materials_count"] += cust.materials.count()
            except Exception:
                pass

    customers = []
    for name, tmap in grouped.items():
        tep_entries = []
        for tep_code, data in sorted(tmap.items()):
            tep_entries.append({
                "tep_code": tep_code,
                "part_code": ", ".join(sorted(data["part_codes"])) if data["part_codes"] else "",
                "materials_count": data["materials_count"],
            })
        selected_tep = tep_entries[0]["tep_code"] if tep_entries else None
        customers.append({
            "customer_name": name,
            "tep_entries": tep_entries,
            "selected_tep": selected_tep,
        })

    context = {"customers": customers, "q": q}
    return render(request, "customer_list.html", context)


def customer_detail(request, tep_code: str):

    import re
    regex = r'(^|,\s*)' + re.escape(tep_code) + r'(,|$)'
    customer = Customer.objects.filter(tep_code__regex=regex).first()
    if not customer:
        raise Http404("Customer not found")

    materials = customer.materials.all().order_by("material_name")
    context = {"customer": customer, "materials": materials, "selected_tep": tep_code}
    return render(request, "customer_detail.html", context)
