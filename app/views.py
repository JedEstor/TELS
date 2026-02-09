import json
from collections import defaultdict
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse

from .models import Customer, TEPCode, Material


def home(request):
    return HttpResponse("Welcome to the Home Page!")


def customer_list(request):
    q = (request.GET.get("q") or "").strip()

    qs = (
        Customer.objects
        .prefetch_related("tep_codes__materials")
        .order_by("customer_name")
    )

    if q:
        qs = qs.filter(
            Q(customer_name__icontains=q)
            | Q(tep_codes__tep_code__icontains=q)
            | Q(tep_codes__part_code__icontains=q)
            | Q(tep_codes__materials__mat_partcode__icontains=q)
            | Q(tep_codes__materials__mat_partname__icontains=q)
            | Q(tep_codes__materials__mat_maker__icontains=q)
        ).distinct()

    grouped = defaultdict(lambda: {
        "parts_by_code": {},               
        "teps_by_part": defaultdict(list) 
    })

    for cust in qs:
        name = cust.customer_name

        for p in cust.parts or []:
            if not isinstance(p, dict):
                continue
            pc = (p.get("Partcode") or "").strip()
            pn = (p.get("Partname") or "").strip()
            if pc and pc not in grouped[name]["parts_by_code"]:
                grouped[name]["parts_by_code"][pc] = pn

        for tep in cust.tep_codes.all():
            grouped[name]["teps_by_part"][tep.part_code].append(tep)

    customers = []

    for name, g in grouped.items():
        parts_by_code = g["parts_by_code"]
        teps_by_part = g["teps_by_part"]

        part_code_options = sorted(parts_by_code.keys())
        part_code_map = {}

        for pc in part_code_options:
            tep_objs = sorted(teps_by_part.get(pc, []), key=lambda t: t.tep_code)

            teps = [
                {
                    "tep_id": t.id,
                    "tep_code": t.tep_code,
                    "materials_count": t.materials.count(),
                }
                for t in tep_objs
            ]

            default_tep = teps[0] if teps else None

            part_code_map[pc] = {
                "part_name": parts_by_code.get(pc, ""),
                "teps": teps,
                "default_tep_id": default_tep["tep_id"] if default_tep else None,
                "default_tep_code": default_tep["tep_code"] if default_tep else "",
                "default_materials_count": default_tep["materials_count"] if default_tep else 0,
            }

        default_pc = part_code_options[0] if part_code_options else ""
        default_tep_options = part_code_map.get(default_pc, {}).get("teps", [])
        default_tep_id = part_code_map.get(default_pc, {}).get("default_tep_id")
        default_tep_code = part_code_map.get(default_pc, {}).get("default_tep_code", "")
        default_materials_count = part_code_map.get(default_pc, {}).get("default_materials_count", 0)

        customers.append({
            "customer_name": name,
            "part_code_options": part_code_options,
            "default_part_code": default_pc,

            "default_tep_options": default_tep_options,
            "default_tep_id": default_tep_id,
            "default_tep_code": default_tep_code,
            "default_materials_count": default_materials_count,

            "part_code_map_json": json.dumps(part_code_map, ensure_ascii=False),
        })

    return render(
        request,
        "customer_list.html",
        {"customers": customers, "q": q}
    )


def customer_detail(request, tep_id: int):
    tep = get_object_or_404(
        TEPCode.objects.select_related("customer"),
        id=tep_id
    )

    materials = (
        Material.objects
        .filter(tep_code=tep)
        .order_by("mat_partname")
    )

    context = {
        "customer": tep.customer,
        "materials": materials,
        "selected_tep": tep.tep_code,
        "selected_part": tep.part_code,
    }

    return render(request, "customer_detail.html", context)
