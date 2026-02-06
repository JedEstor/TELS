from ninja import NinjaAPI
from django.http import JsonResponse
from django.shortcuts import render
import re
from .models import Customer, Material
from .schemas import (
    CustomerIn, CustomerOut,
    MaterialIn, MaterialOut,
    CustomerWithMaterialsOut
)

api = NinjaAPI(title="Sales API")
#api = NinjaAPI(title="Sales API")

def jresponse(data, status=200):
    return JsonResponse(data, status=status, safe=False)



@api.get("/customers", response=list[CustomerWithMaterialsOut],  tags=["GET DETAILS"])
def list_customers(request):
    return Customer.objects.prefetch_related("materials").all()


######new code sa baba
# ...existing code...
def customer_list_page(request):
    qs = Customer.objects.all()
    grouped = {}
    for c in qs:
        name = c.customer_name
        entry = grouped.setdefault(name, {"tep_codes": set(), "part_codes": set()})
        if c.tep_code:
            for code in (s.strip() for s in c.tep_code.split(",") if s.strip()):
                entry["tep_codes"].add(code)
        if c.part_code:
            for code in (s.strip() for s in c.part_code.split(",") if s.strip()):
                entry["part_codes"].add(code)

    customers = [
        {
            "customer_name": name,
            "tep_codes": list(sorted(entry["tep_codes"])),    # ensure list for template
            "part_codes": ", ".join(sorted(entry["part_codes"])),
        }
        for name, entry in grouped.items()
    ]

    return render(request, "customer_list.html", {"customers": customers})
# ...existing code...
# ...existing code... end here
"""
@api.post("/customers", response=CustomerOut,  tags=["CREATE ORDER"])
def create_customer(request, payload: CustomerIn):
    customer = Customer.objects.create(**payload.dict())
    return customer
"""
#start
"""
@api.post("/customers", tags=["CREATE ORDER"])
def create_customer(request, payload: CustomerIn):

    if Customer.objects.filter(tep_code=payload.tep_code).exists():
        return JsonResponse({"error": "TEP code already exists"}, status=409)

    try:
        customer = Customer.objects.create(
            customer_name=payload.customer_name,
            part_code=payload.part_code,
            tep_code=payload.tep_code
        )

        return JsonResponse(
            {
                "message": "Customer created successfully",
                "id": customer.id,
                "customer_name": customer.customer_name,
                "part_code": customer.part_code,
                "tep_code": customer.tep_code,
            },
            status=200
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
        """
#end

"""
@api.put("/customers/{customer_id}", response=CustomerOut,  tags=["UPDATE"])
def update_customer(request, customer_id: int, payload: CustomerIn):
    customer = Customer.objects.get(id=customer_id)
    for k, v in payload.dict().items():
     customer.save()
    return customer
"""
######################
"""" 
@api.put("/customers/{customer_id}", tags=["UPDATE"])
def update_customer(request, customer_id: int, payload: CustomerIn):

    try:
        customer = Customer.objects.get(id=customer_id)

        customer.customer_name = payload.customer_name
        customer.part_code = payload.part_code
        # customer.tep_code = payload.tep_code

        customer.save()

        return JsonResponse(
            {
                "message": "Customer updated successfully",
                "id": customer.id,
                "customer_name": customer.customer_name,
                "part_code": customer.part_code,
                "tep_code": customer.tep_code,
            },
            status=200
        )
    except Customer.DoesNotExist:
        return JsonResponse({"error": "Customer not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
"""
# ......

@api.post("/customers", tags=["CREATE ORDER"])
def create_customer(request, payload: CustomerIn):

    def _merge_codes(existing: str, new: str) -> str:
        items = [s.strip() for s in (existing or "").split(",") if s.strip()]
        if new and new.strip() not in items:
            items.append(new.strip())
        return ", ".join(items)

    try:
        # if customer_name exists -> append codes
        customer = Customer.objects.filter(customer_name=payload.customer_name).first()
        if customer:
            customer.tep_code = _merge_codes(customer.tep_code, payload.tep_code)
            customer.part_code = _merge_codes(customer.part_code, payload.part_code)
            customer.part_name = _merge_codes(customer.part_name, payload.part_name)
            customer.save()
            return JsonResponse(
                {
                    "message": "Customer updated (codes appended) successfully",
                    "id": customer.id,
                    "customer_name": customer.customer_name,
                    "part_code": customer.part_code,
                    "tep_code": customer.tep_code,
                    "part_name": customer.part_name,
                },
                status=200
            )

        # else create new customer
        customer = Customer.objects.create(
            customer_name=payload.customer_name,
            part_code=payload.part_code,
            tep_code=payload.tep_code,
            part_name=payload.part_name
        )

        return JsonResponse(
            {
                "message": "Customer created successfully",
                "id": customer.id,
                "customer_name": customer.customer_name,
                "part_code": customer.part_code,
                "tep_code": customer.tep_code,
                "part_name": customer.part_name,
            },
            status=200
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
# ...existing code...
##########

@api.delete("/customers/{customer_id}",  tags=["REMOVE"])
def delete_customer(request, customer_id: int):
    Customer.objects.filter(id=customer_id).delete()
    return jresponse({"message": "Customer deleted"})


# hndi nalabas ang value
#@api.get("/materials", response=list[MaterialOut],  tags=["GET DETAILS"])
#def list_materials(request, payload: MaterialIn):
#    return Material.objects.all()

@api.get("/materials", response=list[MaterialOut],  tags=["GET DETAILS"])
def list_materials(request):
    return Material.objects.all()

"""
@api.post("/customers/{tep_code}/materials", response=MaterialOut,  tags=["CREATE ORDER"])
   customer = Customer.objects.get(tep_code=tep_code)
    material = Material.objects.create(customer=customer, **payload.dict())
    return material
"""

@api.post("/customers/{tep_code}/materials", tags=["CREATE ORDER"])
def create_material_for_customer(request, tep_code: str, payload: MaterialIn):

    try:
        try:
            customer = Customer.objects.get(tep_code=tep_code)
        except Customer.DoesNotExist:
            regex = r'(^|,\s*)' + re.escape(tep_code) + r'(,|$)'
            customer = Customer.objects.filter(tep_code__regex=regex).first()
            if not customer:
                raise Customer.DoesNotExist()

        material = Material.objects.create(
            customer=customer,
            maker=payload.maker,
            material_part_code=payload.material_part_code,
            material_name=payload.material_name,
            unit=payload.unit,
            dim_qty=payload.dim_qty,
            loss_percent=payload.loss_percent,
            total=payload.total,
        )

        return JsonResponse(
            {
                "message": "Material created successfully",
                "id": material.id,
                "tep_code": customer.tep_code,
                "maker": material.maker,
                "material_part_code": material.material_part_code,
                "material_name": material.material_name,
                "unit": material.unit,
                "dim_qty": material.dim_qty,
                "loss_percent": material.loss_percent,
                "total": material.total,
            },
            status=200
        )
    except Customer.DoesNotExist:
        return JsonResponse({"error": "Customer not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

"""
@api.put("/materials/{material_id}", response=MaterialOut,  tags=["UPDATE"])
def update_material(request, material_id: int, payload: MaterialIn):
    material = Material.objects.get(id=material_id)
    for k, v in payload.dict().items():
        setattr(material, k, v)
    material.save()
    return material
"""

@api.put("/materials/{material_id}", tags=["UPDATE"])
def update_material(request, material_id: int, payload: MaterialIn):

    try:
        material = Material.objects.get(id=material_id)

        material.maker = payload.maker
        material.material_part_code = payload.material_part_code
        material.material_name = payload.material_name
        material.unit = payload.unit
        material.dim_qty = payload.dim_qty
        material.loss_percent = payload.loss_percent
        material.total = payload.total

        material.save()

        return JsonResponse(
            {
                "message": "Material updated successfully",
                "id": material.id,
                "customer_id": material.customer_id,
                "maker": material.maker,
                "material_part_code": material.material_part_code,
                "material_name": material.material_name,
                "unit": material.unit,
                "dim_qty": material.dim_qty,
                "loss_percent": material.loss_percent,
                "total": material.total,
            },
            status=200
        )
    except Material.DoesNotExist:
        return JsonResponse({"error": "Material not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)



@api.delete("/materials/{material_id}",  tags=["REMOVE"])
def delete_material(request, material_id: int):
    Material.objects.filter(id=material_id).delete()
    return jresponse({"message": "Material deleted"})



@api.get("/customers/{tep_code}/details", response=CustomerWithMaterialsOut,  tags=["GET DETAILS"])
def customer_details_by_tep_code(request, tep_code: str):
    try:
        customer = Customer.objects.get(tep_code=tep_code)
    except Customer.DoesNotExist:
        regex = r'(^|,\s*)' + re.escape(tep_code) + r'(,|$)'
        customer = Customer.objects.filter(tep_code__regex=regex).first()
        if not customer:
            return JsonResponse({"error": "Customer not found"}, status=404)

    materials = list(customer.materials.all())

    return {
        "id": customer.id,
        "customer_name": customer.customer_name,
        "part_code": customer.part_code,
        "tep_code": customer.tep_code,
        "part_name": customer.part_name,
        "materials": materials,
    }
