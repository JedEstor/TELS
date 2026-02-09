from ninja import NinjaAPI, File
from ninja.files import UploadedFile
from django.http import JsonResponse
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.db.models import Prefetch
import csv, io, re
from .models import Customer, TEPCode, Material, CustomerCSV, MaterialList
#new, naglagay nung MaterialList sa itaas na import
from .schemas import (
    CustomerIn, CustomerOut, CustomerFullOut,
    TEPCodeIn, TEPCodeOut,
    MaterialIn, MaterialOut, MaterialListIn

)


api = NinjaAPI(title="Sales API")

def jresponse(data, status=200):
    return JsonResponse(data, status=status, safe=False)

import re

def _normalize_space(s):
    return re.sub(r"\s+", " ", (s or "").strip())

def _unique_partname_for_customer(customer, base_name, part_code):
    """
    Unique Partname per customer.parts.
    If base_name already exists for a different Partcode, returns base_name 1, base_name 2, ...
    """
    base_name = _normalize_space(base_name)
    part_code = _normalize_space(part_code)

    parts = customer.parts or []

    # If this Partcode already exists, keep its existing Partname
    for p in parts:
        if isinstance(p, dict) and _normalize_space(p.get("Partcode")) == part_code:
            existing = _normalize_space(p.get("Partname"))
            return existing or base_name

    # collect existing part names
    existing_names = set()
    for p in parts:
        if isinstance(p, dict):
            n = _normalize_space(p.get("Partname"))
            if n:
                existing_names.add(n.lower())

    # base name is free
    if base_name.lower() not in existing_names:
        return base_name

    # find next suffix
    i = 1
    while True:
        candidate = f"{base_name} {i}"
        if candidate.lower() not in existing_names:
            return candidate
        i += 1

def _ensure_customer_part_entry(customer, part_code, part_name):
    """
    Ensures customer.parts contains Partcode.
    If not exists, adds it with unique Partname (Tape, Tape 1, Tape 2...).
    Returns (changed: bool, used_partname: str)
    """
    part_code = _normalize_space(part_code)
    part_name = _normalize_space(part_name) or part_code

    parts = customer.parts or []

    # already exists?
    for p in parts:
        if isinstance(p, dict) and _normalize_space(p.get("Partcode")) == part_code:
            used = _normalize_space(p.get("Partname")) or part_name
            return False, used

    unique_name = _unique_partname_for_customer(customer, part_name, part_code)

    parts.append({"Partcode": part_code, "Partname": unique_name})
    customer.parts = parts
    customer.save()

    return True, unique_name



@api.get("/customers", tags=["CUSTOMER"])
def customers_tree(request, q: str = ""):
    """
    Returns JSON exactly like:
    {
      "customer_name": "...",
      "Customer Part": [
        {
          "Partcode": "...",
          "Partname": "...",
          "TEP Codes": [
            {
              "TEP Code": "...",
              "Materials": [...]
            }
          ]
        }
      ]
    }
    """
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

    out = []

    for cust in qs:
        parts = cust.parts or []
        customer_parts = []

        for p in parts:
            if not isinstance(p, dict):
                continue

            partcode = (p.get("Partcode") or "").strip()
            partname = (p.get("Partname") or "").strip()
            if not partcode:
                continue

            tep_list = []
            tep_objs = [t for t in cust.tep_codes.all() if t.part_code == partcode]

            for tep in tep_objs:
                mats = []
                for m in tep.materials.all():
                    mats.append({
                        "mat_partcode": m.mat_partcode,
                        "mat_partname": m.mat_partname,
                        "mat_maker": m.mat_maker,
                        "unit": m.unit,
                        "dim_qty": m.dim_qty,
                        "loss_percent": m.loss_percent,
                        "total": m.total,
                    })

                tep_list.append({
                    "TEP Code": tep.tep_code,
                    "Materials": mats
                })

            customer_parts.append({
                "Partcode": partcode,
                "Partname": partname,
                "TEP Codes": tep_list
            })

        out.append({
            "customer_name": cust.customer_name,
            "Customer Part": customer_parts
        })

    return jresponse(out, status=200)


@api.post("/customers", response=CustomerOut, tags=["CUSTOMER"])
def create_customer(request, payload: CustomerIn):
    parts = payload.parts or []

    for i, p in enumerate(parts):
        if not p.Partcode or not p.Partname:
            return jresponse({"error": f"parts[{i}] must contain Partcode and Partname"}, status=400)

    customer = Customer.objects.create(
        customer_name=payload.customer_name,
        parts=[p.dict() for p in parts],
    )
    return customer


@api.put("/customers/{customer_id}", response=CustomerOut, tags=["CUSTOMER"])
def update_customer(request, customer_id: int, payload: CustomerIn):
    customer = get_object_or_404(Customer, id=customer_id)
    customer.customer_name = payload.customer_name
    customer.parts = [p.dict() for p in (payload.parts or [])]
    customer.save()
    return customer


@api.delete("/customers/{customer_id}", tags=["CUSTOMER"])
def delete_customer(request, customer_id: int):
    Customer.objects.filter(id=customer_id).delete()
    return jresponse({"message": "Customer deleted"})



@api.get("/customers/{customer_id}/tep-codes", response=list[TEPCodeOut], tags=["TEP"])
def list_tep_codes(request, customer_id: int, part_code: str = ""):
    customer = get_object_or_404(Customer, id=customer_id)
    qs = customer.tep_codes.all().order_by("tep_code")
    if part_code:
        qs = qs.filter(part_code=part_code)
    return qs


@api.post("/parts/{part_code}/tep-codes", response=TEPCodeOut, tags=["TEP"])
def create_tep_code_by_part_code(request, part_code: str, payload: TEPCodeIn):
    part_code = (part_code or "").strip()
    tep_code = (payload.tep_code or "").strip()

    if not part_code:
        return jresponse({"error": "part_code is required"}, status=400)
    if not tep_code:
        return jresponse({"error": "tep_code is required"}, status=400)

    customer = None
    for c in Customer.objects.all():
        parts = c.parts or []
        if any(
            isinstance(p, dict) and str(p.get("Partcode", "")).strip() == part_code
            for p in parts
        ):
            customer = c
            break

    if not customer:
        return jresponse({"error": f"part_code '{part_code}' not found in any customer.parts"}, status=404)

    tep, created = TEPCode.objects.get_or_create(
        customer=customer,
        part_code=part_code,
        tep_code=tep_code,
    )

    return tep



@api.delete("/tep-codes/{tep_code}", tags=["TEP"])
def delete_tep_code_by_code(request, tep_code: str):
    tep_code = (tep_code or "").strip()

    if not tep_code:
        return jresponse({"error": "tep_code is required"}, status=400)

    deleted_count, _ = TEPCode.objects.filter(tep_code=tep_code).delete()

    if deleted_count == 0:
        return jresponse(
            {"error": f"TEP code '{tep_code}' not found"},
            status=404
        )

    return jresponse(
        {"message": f"TEP code '{tep_code}' deleted successfully"},
        status=200
    )


@api.get("/tep-codes/{tep_code}/materials", response=list[MaterialOut], tags=["MATERIAL"])
def list_materials_by_tep_code(request, tep_code: str):
    tep_code = (tep_code or "").strip()

    if not tep_code:
        return jresponse({"error": "tep_code is required"}, status=400)

    tep = get_object_or_404(TEPCode, tep_code=tep_code)

    return tep.materials.all().order_by("mat_partname")


"""
@api.post("/tep-codes/by-code/{tep_code}/materials", response=MaterialOut, tags=["MATERIAL"])
def create_material_by_tep_code(
    request,
    tep_code: str,
    payload: MaterialIn,
    part_code: str = "",
    customer_name: str = "",
):
    qs = TEPCode.objects.select_related("customer").filter(tep_code=tep_code)

    if part_code:
        qs = qs.filter(part_code=part_code)
    if customer_name:
        qs = qs.filter(customer__customer_name=customer_name)

    tep = qs.first()
    if not tep:
        return jresponse(
            {"error": "TEP code not found. Provide part_code and/or customer_name."},
            status=404,
        )

    material = Material.objects.create(
        tep_code=tep,
        mat_partcode=payload.mat_partcode,
        mat_partname=payload.mat_partname,
        mat_maker=payload.mat_maker,
        unit=payload.unit,
        dim_qty=payload.dim_qty,
        loss_percent=payload.loss_percent,
        total=payload.total,
    )
    return material
"""
from django.db import IntegrityError, transaction

"""@api.post("/tep-codes/by-code/{tep_code}/materials", response=MaterialOut, tags=["MATERIAL"])
def create_material_by_tep_code(
    request,
    tep_code: str,
    payload: MaterialIn,
    part_code: str = "",
    customer_name: str = "",
):
    tep_code = (tep_code or "").strip()
    if not tep_code:
        return jresponse({"error": "tep_code is required"}, status=400)

    qs = TEPCode.objects.select_related("customer").filter(tep_code=tep_code)

    if part_code:
        qs = qs.filter(part_code=part_code.strip())
    if customer_name:
        qs = qs.filter(customer__customer_name=customer_name.strip())

    tep = qs.first()
    if not tep:
        return jresponse(
            {"error": "TEP code not found. Provide part_code and/or customer_name."},
            status=404,
        )

    mat_partcode = (payload.mat_partcode or "").strip()
    if not mat_partcode:
        return jresponse({"error": "mat_partcode is required"}, status=400)

    try:
        with transaction.atomic():
            material, created = Material.objects.get_or_create(
                tep_code=tep,
                mat_partcode=mat_partcode,
                defaults={
                    "mat_partname": payload.mat_partname,
                    "mat_maker": payload.mat_maker,
                    "unit": payload.unit,
                    "dim_qty": payload.dim_qty,
                    "loss_percent": payload.loss_percent,
                    "total": payload.total,
                },
            )
    except IntegrityError:
        material = Material.objects.filter(tep_code=tep, mat_partcode=mat_partcode).first()
        created = False


    return material"""

#new syntax for the post
"""@api.post("/tep-codes/by-code/{tep_code}/materials", response=MaterialOut, tags=["MATERIAL"])
def create_material_by_tep_code(
    request,
    tep_code:str,
    payload: MaterialIn,
    part_code: str = "",
    customer_name: str = "",
):
    tep_code = (tep_code or "").strip()
    mat_partcode = (payload.mat_partcode or "").strip()

    if not tep_code:
        return jresponse({"error": "tep_code is required"}, status=400)
    if not mat_partcode:
        return jresponse({"error": "mat_partcode is required"}, status=400)
    
    qs = TEPCode.objects.select_related("customer").filter(tep_code=tep_code)

    if part_code:
        qs = qs.filter(part_code=part_code.strip())
    if customer_name:
        qs = qs.filter(customer__customer_name=customer_name.strip())

    tep = qs.first()
    if not tep:
        return jresponse(
            {"error": "TEP code not found. Provide part_code and/or customer_name."},
            status=404,
        )
    
    master = MaterialList.objects.filter(mat_partcode=mat_partcode).first()
    if not master:
        return jresponse(
            {"error": f"mat_partcode '{mat_partcode}' not found in MaterialList (master list)."},
            status=404,
        )

    loss = payload.loss_percent if payload.loss_percent is not None else 10.0
    total = round(float(payload.dim_qty) * (1+(float(loss) / 100.0)), 4)

    material, created = Material.objects.get_or_create(
        tep_code=tep,
        mat_partcode=master.mat_partcode,
        defaults={
            "mat_partname": master.mat_partname,
            "mat_maker": master.mat_maker,
            "unit": master.unit,
            "dim_qty": payload.dim_qty,
            "loss_percent": loss,
            "total": total,
        }
    )

    if not created:
        return jresponse(
            {
                "error": "Material already exists for this TEP code.",
                "tep_code": tep.tep_code,
                "mat_partcode": material.mat_partcode,
            },
            status=409
        )
    return material"""
####
@api.post("/tep-codes/by-code/{tep_code}/materials", response=MaterialOut, tags=["MATERIAL"])
def create_material_by_tep_code(
    request,
    tep_code: str,
    payload: MaterialIn,
    customer_name: str = "",
    part_code: str = "",   # optional disambiguation
):
    tep_code = (tep_code or "").strip()
    customer_name = (customer_name or "").strip()
    part_code = (part_code or "").strip()
    mat_partcode = (payload.mat_partcode or "").strip()

    if not tep_code:
        return jresponse({"error": "tep_code is required"}, status=400)
    if not mat_partcode:
        return jresponse({"error": "mat_partcode is required"}, status=400)

    qs = TEPCode.objects.select_related("customer").filter(tep_code=tep_code)

    if customer_name:
        qs = qs.filter(customer__customer_name=customer_name)
    if part_code:
        qs = qs.filter(part_code=part_code)

    tep = qs.first()
    if not tep:
        return jresponse(
            {"error": "TEP code not found. Provide part_code and/or customer_name."},
            status=404,
        )

    # ✅ Ensure customer.parts has the part entry (and applies Tape/Tape 1 logic)
    # Uses the TEPCode.part_code and the best-guess base name from existing parts (or part_code if missing)
    existing_partname = ""
    for p in (tep.customer.parts or []):
        if isinstance(p, dict) and str(p.get("Partcode", "")).strip() == tep.part_code:
            existing_partname = str(p.get("Partname", "")).strip()
            break

    base_partname = existing_partname or tep.part_code
    _ensure_customer_part_entry(tep.customer, tep.part_code, base_partname)

    master = MaterialList.objects.filter(mat_partcode=mat_partcode).first()
    if not master:
        return jresponse({"error": f"mat_partcode '{mat_partcode}' not found in master list."}, status=404)

    loss = payload.loss_percent if payload.loss_percent is not None else 10.0
    total = round(float(payload.dim_qty) * (1 + (float(loss) / 100.0)), 4)

    material, created = Material.objects.get_or_create(
        tep_code=tep,
        mat_partcode=master.mat_partcode,
        defaults={
            "mat_partname": master.mat_partname,
            "mat_maker": master.mat_maker,
            "unit": master.unit,
            "dim_qty": payload.dim_qty,
            "loss_percent": loss,
            "total": total,
        }
    )

    if not created:
        return jresponse(
            {"error": "Material already exists for this TEP + mat_partcode."},
            status=409
        )

    return material





@api.put("/tep-codes/{tep_code}/materials/{mat_partcode}",
    response=MaterialOut,
    tags=["MATERIAL"]
)
def update_material_by_tep_and_partcode(
    request,
    tep_code: str,
    mat_partcode: str,
    payload: MaterialIn
):
    tep_code = (tep_code or "").strip()
    mat_partcode = (mat_partcode or "").strip()

    if not tep_code:
        return jresponse({"error": "tep_code is required"}, status=400)

    if not mat_partcode:
        return jresponse({"error": "mat_partcode is required"}, status=400)

    material = get_object_or_404(
        Material,
        tep_code__tep_code=tep_code,
        mat_partcode=mat_partcode
    )

    material.mat_partcode = payload.mat_partcode
    material.mat_partname = payload.mat_partname
    material.mat_maker = payload.mat_maker
    material.unit = payload.unit
    material.dim_qty = payload.dim_qty
    material.loss_percent = payload.loss_percent
    material.total = payload.total

    material.save()

    return material



@api.delete("/tep-codes/{tep_code}/materials/{mat_partcode}", tags=["MATERIAL"])
def delete_material_by_tep_and_partcode(request, tep_code: str, mat_partcode: str):
    tep_code = (tep_code or "").strip()
    mat_partcode = (mat_partcode or "").strip()

    if not tep_code:
        return jresponse({"error": "tep_code is required"}, status=400)

    if not mat_partcode:
        return jresponse({"error": "mat_partcode is required"}, status=400)

    deleted_count, _ = Material.objects.filter(
        tep_code__tep_code=tep_code,
        mat_partcode=mat_partcode
    ).delete()

    if deleted_count == 0:
        return jresponse(
            {
                "error": f"No material found for tep_code '{tep_code}' "
                         f"and mat_partcode '{mat_partcode}'"
            },
            status=404
        )

    return jresponse(
        {
            "message": "Material deleted successfully",
            "tep_code": tep_code,
            "mat_partcode": mat_partcode,
            "deleted_records": deleted_count
        },
        status=200
    )


"""@api.post("/upload-csv", tags=["CSV"])
def upload_csv(request, file: UploadedFile = File(...)):
    if not file:
        return jresponse({"error": "No file uploaded."}, status=400)

    try:
        content = file.read().decode("utf-8")
        csv_file = io.StringIO(content)
        reader = csv.DictReader(csv_file)
        reader.fieldnames = [h.strip().lstrip("\ufeff") for h in reader.fieldnames]

        inserted = 0
        updated = 0

        def fnum(x, default=0.0):
            try:
                return float(x)
            except Exception:
                return float(default)

        with transaction.atomic():
            CustomerCSV.objects.create(csv_file=file)

            for row in reader:
                customer_name = (row.get("customer_name") or "").strip()
                partcode = (row.get("Partcode") or row.get("part_code") or "").strip()
                partname = (row.get("Partname") or row.get("part_name") or "").strip()
                tep_code = (row.get("tep_code") or "").strip()

                mat_partcode = (row.get("mat_partcode") or "").strip()
                mat_partname = (row.get("mat_partname") or "").strip()
                mat_maker = (row.get("mat_maker") or "").strip()
                unit = (row.get("unit") or "dim_qty").strip()

                dim_qty = fnum(row.get("dim_qty"), 0)
                loss_percent = fnum(row.get("loss_percent"), 10.0)
                total = fnum(row.get("total"), 0)

                if not (customer_name and partcode and partname and tep_code and mat_partcode):
                    continue

                customer, _ = Customer.objects.get_or_create(customer_name=customer_name)

                parts = customer.parts or []
                exists = any(
                    isinstance(p, dict)
                    and str(p.get("Partcode", "")).strip() == partcode
                    for p in parts
                )
                if not exists:
                    parts.append({"Partcode": partcode, "Partname": partname})
                    customer.parts = parts
                    customer.save()

                tep, _ = TEPCode.objects.get_or_create(
                    customer=customer,
                    part_code=partcode,
                    tep_code=tep_code,
                )

                mat, created = Material.objects.get_or_create(
                    tep_code=tep,
                    mat_partcode=mat_partcode,
                    defaults={
                        "mat_partname": mat_partname,
                        "mat_maker": mat_maker,
                        "unit": unit,
                        "dim_qty": dim_qty,
                        "loss_percent": loss_percent,
                        "total": total,
                    }
                )

                if created:
                    inserted += 1
                else:
                    mat.mat_partname = mat_partname or mat.mat_partname
                    mat.mat_maker = mat_maker or mat.mat_maker
                    mat.unit = unit or mat.unit
                    mat.dim_qty = dim_qty if dim_qty != 0 else mat.qty
                    mat.loss_percent = loss_percent if loss_percent != 0 else mat.loss_percent
                    mat.total = total if total != 0 else mat.total
                    mat.save()
                    updated += 1

        return jresponse(
            {
                "message": "CSV uploaded successfully",
                "inserted_materials": inserted,
                "updated_materials": updated,
            },
            status=200
        )

    except Exception as e:
        return jresponse({"error": str(e)}, status=500)"""
#new code for post
@api.post("/upload-csv", tags=["CSV"])
def upload_csv(request, file: UploadedFile = File(...)):
    if not file:
        return jresponse({"error": "No file uploaded."}, status=400)
    
    try:
        content = file.read().decode("utf-8")
        csv_file = io.StringIO(content)
        reader = csv.DictReader(csv_file)

        reader.fieldnames = [h.strip().lstrip("\ufeff") for h in (reader.fieldname or [])]
        inserted = 0
        updated = 0
        master_inserted = 0
        master_updated = 0

        ALLOWED_UNITS = {"pc", "pcs", "m"}

        def fnum(x, default=0.0):
            try:
                if x is None:
                    return float(default)
                s = str(x).strip()
                if s == "":
                    return float(default)
                return float(s)
            except Exception:
                return float(default)
        
        def sget(row, *keys, default=""):
            for k in keys:
                v = row.get(k)
                if v is not None and str(v).strip() != "":
                    return str(v).strip()
            return default
        
        with transaction.atomic():
            CustomerCSV.objects.create(csv_file=file)

            for row in reader:
               

                mat_partcode = sget(row, "mat_partcode")
                mat_partname = sget(row, "mat_partname")
                mat_maker = sget(row, "mat_maker")
                unit = sget(row, "unit", default="pc").lower()

                if unit not in ALLOWED_UNITS:
                    unit = "pc"

                dim_qty = fnum(row.get("dim_qty"), 0.0)
                loss_percent = fnum(row.get("loss_percent"), 10.0)

                total_csv = row.get("total")
                if total_csv is None or str(total_csv).strip() == "":
                    total = round(float(dim_qty) * (1 + (float(loss_percent) / 100.0)), 4)
                else:
                    total = round(fnum(total_csv, 0.0), 4)
                
                if not (customer_name and partcode and partname and tep_code and mat_partcode):
                    continue

                master, m_created = MaterialList.objects.get_or_create(
                    mat_partcode=mat_partcode,
                    defaults={
                        "mat_partname": mat_partname or mat_partcode,
                        "mat_maker": mat_maker or "Unknown",
                        "unit": unit,
                    }
                )
                if m_created:
                    master_inserted += 1
                else:
                    changed = False
                    if mat_partname and master.mat_partname != mat_partname:
                        master.mat_partname = mat_partname
                        change = True
                    if mat_maker and master.mat_maker != mat_maker:
                        master.mat_maker = mat_maker
                        changed = True
                    if unit and master.unit != unit:
                        master.unit = unit
                        changed = True
                    if changed:
                        master.save()
                        master_updated += 1

                customer, _ = Customer.objects.get_or_create(customer_name=customer_name)

                """parts = customer.parts or []
                exists = any(
                    isinstance(p, dict)
                    and str(p.get("Partcode", "")).strip() == partcode
                    for p in parts
                )
                if not exists:
                    parts.append({"Partcode": partcode, "Partname": partname})
                    customer.parts = parts
                    customer.save()"""
                _ensure_customer_part_entry(customer, partcode, partname)


                tep, _ = TEPCode.objects.get_or_create(
                    customer=customer,
                    part_code=partcode,
                    tep_code=tep_code,
                )

                mat, created = Material.objects.get_or_create(
                    tep_code=tep,
                    mat_partcode=master.mat_partcode,
                    defaults={
                        "mat_partname": master.mat_partname,
                        "mat_maker": master.mat_maker,
                        "unit": master.unit,
                        "dim_qty": dim_qty,
                        "loss_percent": loss_percent,
                        "total": total,
                    }
                )

                if created:
                    inserted += 1
                else:
                    mat.mat_partname = master.mat_partname
                    mat.mat_maker = master.mat_maker
                    mat.unit = master.unit

                    if dim_qty != 0:
                        mat.dim_qty = dim_qty
                    if loss_percent != 0:
                        mat.loss_percent = loss_percent
                    
                    if total_csv is None or str(total_csv).strip() == "":
                        mat.total = round(float(mat.dim_qty) * (1 + (float(mat.loss_percent) / 100.0)), 4)
                    else:
                        mat.total = total

                    mat.save()
                    updated += 1
        
        return jresponse(
            {
                "message": "CSV uploaded successfully (master list + materials)",
                "master_insertes": master_inserted,
                "master_updated": master_updated,
                "inserted_materials": inserted,
                "updated_materials": updated,
            },
            status=200
        )
    
    except Exception as e:
        return jresponse({"error": str(e)}, status=500)

    

#new code for the output    
@api.get("/output-format", tags=["GET DETAILS"])
def output_format(request):
    customers = Customer.objects.prefetch_related(
        Prefetch(
            "tep_codes",
            queryset=TEPCode.objects.prefetch_related(
                Prefetch("materials", queryset=Material.objects.all().order_by("mat_partname"))
            ).all()
        )
    ).all().order_by("customer_name")

    result = []

    for customer in customers:
        teps_by_part = {}
        for tep in customer.tep_codes.all():
            teps_by_part.setdefault(tep.part_code, []).append(tep)

        parts_out = []
        for p in (customer.parts or []):
            if not isinstance(p, dict):
                continue

            partcode = str(p.get("Partcode", "")).strip()
            partname = str(p.get("Partname", "")).strip()

            if not partcode:
                continue

            tep_codes_out = []
            for tep in teps_by_part.get(partcode, []):
                mats_out = []
                for m in tep.materials.all():
                    mats_out.append({
                        "mat_partcode": m.mat_partcode,
                        "mat_partname": m.mat_partname,
                        "mat_maker": m.mat_maker,
                        "unit": m.unit,
                        "dim_qty": m.dim_qty,
                        "loss_percent": m.loss_percent,
                        "total": m.total,
                    })
                tep_codes_out.append({
                    "TEP Code": tep.tep_code,
                    "Materials": mats_out
                })
            parts_out.append({
                "Partcode": partcode,
                "Partname": partname,
                "TEP Codes": tep_codes_out
            })
        result.append({
            "customer_name": customer.customer_name,
            "Customer Part": parts_out
        })
    return jresponse(result)


@api.post("/master/materials", tags=["MASTER LIST"])
def create_master_material(request, payload: MaterialListIn):
    code = (payload.mat_partcode or "").strip()

    if not code:
        return jresponse({"error": "mat_partcode is required"}, status=400)
    
    obj, created = MaterialList.objects.get_or_create(
        mat_partcode=code,
        defaults = {
            "mat_partname": (payload.mat_partname or "").strip(),
            "mat_maker": (payload.mat_maker or "").strip(),
            "unit": (payload.unit or "").strip(),
        }
    )
    if not created:
        return jresponse({"error": "mat_partcode already exists in master list"}, status=409)
    return jresponse(
        {
            "message": "Master material created",
            "mat_partcode": obj.mat_partcode,
            "mat_partname": obj.mat_partname,
            "mat_maker": obj.mat_maker,
            "unit": obj.unit,
        },
        status=201
    )


