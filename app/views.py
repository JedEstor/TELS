import json
import csv
import io
from collections import defaultdict

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test

from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Customer, TEPCode, Material, MaterialList

from .forms import EmployeeCreateForm


def is_admin(user):
    return user.is_authenticated and user.is_superuser


def can_edit(user):
    return user.is_authenticated and user.is_staff


def home(request):
    return HttpResponse("Welcome to the Home Page!")


def login_view(request):
    error = ""

    if request.method == "POST":
        employee_id = (request.POST.get("employee_id") or "").strip()
        password = request.POST.get("password") or ""

        user = authenticate(request, username=employee_id, password=password)

        if user is not None and user.is_active:
            login(request, user)

            if user.is_superuser:
                return redirect("app:admin_dashboard")

            if user.is_staff:
                return redirect("app:customer_list")

            return redirect("app:customer_list")
        else:
            error = "Invalid Employee ID or password"

    return render(request, "login.html", {"error": error})


def build_customer_table(q: str):
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
        "teps_by_part": defaultdict(list),
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

        customers.append({
            "customer_name": name,
            "part_code_options": part_code_options,
            "default_part_code": default_pc,

            "default_tep_options": part_code_map.get(default_pc, {}).get("teps", []),
            "default_tep_id": part_code_map.get(default_pc, {}).get("default_tep_id"),
            "default_tep_code": part_code_map.get(default_pc, {}).get("default_tep_code", ""),
            "default_materials_count": part_code_map.get(default_pc, {}).get("default_materials_count", 0),

            "part_code_map_json": json.dumps(part_code_map, ensure_ascii=False),
        })

    return customers


from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse

from .models import Customer, TEPCode, Material, MaterialList
from .forms import EmployeeCreateForm  # we’ll reuse if you want later


def is_admin(user):
    return user.is_authenticated and user.is_superuser


@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    tab = (request.GET.get("tab") or "customers").strip().lower()

    # =========================
    # POST ACTIONS (materials + users)
    # =========================
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        # -------- MATERIALS actions --------
        if action == "add_material":
            mat_partcode = (request.POST.get("mat_partcode") or "").strip()
            mat_partname = (request.POST.get("mat_partname") or "").strip()
            mat_maker = (request.POST.get("mat_maker") or "").strip()
            unit = (request.POST.get("unit") or "").strip().lower()

            allowed_units = {"pc", "pcs", "m"}
            if unit not in allowed_units:
                unit = "pc"

            if not mat_partcode:
                messages.error(request, "Part Code is required.")
                return redirect(reverse("app:admin_dashboard") + "?tab=materials")

            try:
                obj, created = MaterialList.objects.get_or_create(
                    mat_partcode=mat_partcode,
                    defaults={
                        "mat_partname": mat_partname or mat_partcode,
                        "mat_maker": mat_maker or "Unknown",
                        "unit": unit,
                    }
                )

                if created:
                    messages.success(request, f"Added material: {mat_partcode}")
                else:
                    changed = False
                    if mat_partname and obj.mat_partname != mat_partname:
                        obj.mat_partname = mat_partname
                        changed = True
                    if mat_maker and obj.mat_maker != mat_maker:
                        obj.mat_maker = mat_maker
                        changed = True
                    if unit and obj.unit != unit:
                        obj.unit = unit
                        changed = True

                    if changed:
                        obj.save()
                        messages.success(request, f"Updated material: {mat_partcode}")
                    else:
                        messages.info(request, f"No changes for: {mat_partcode}")

            except Exception as e:
                messages.error(request, f"Failed to save material: {e}")

            return redirect(reverse("app:admin_dashboard") + "?tab=materials")

        if action == "update_material":
            mat_id = (request.POST.get("mat_id") or "").strip()
            mat_partcode = (request.POST.get("mat_partcode") or "").strip()
            mat_partname = (request.POST.get("mat_partname") or "").strip()
            mat_maker = (request.POST.get("mat_maker") or "").strip()
            unit = (request.POST.get("unit") or "").strip().lower()

            allowed_units = {"pc", "pcs", "m"}
            if unit not in allowed_units:
                unit = "pc"

            if not mat_id:
                messages.error(request, "Missing material ID.")
                return redirect(reverse("app:admin_dashboard") + "?tab=materials")

            try:
                obj = MaterialList.objects.get(id=mat_id)

                if not mat_partcode:
                    messages.error(request, "Part Code is required.")
                    return redirect(reverse("app:admin_dashboard") + "?tab=materials")

                if mat_partcode != obj.mat_partcode:
                    if MaterialList.objects.filter(mat_partcode=mat_partcode).exclude(id=obj.id).exists():
                        messages.error(request, f"Part Code already exists: {mat_partcode}")
                        return redirect(reverse("app:admin_dashboard") + "?tab=materials")

                obj.mat_partcode = mat_partcode
                obj.mat_partname = mat_partname or mat_partcode
                obj.mat_maker = mat_maker or "Unknown"
                obj.unit = unit
                obj.save()

                messages.success(request, f"Saved changes: {obj.mat_partcode}")

            except MaterialList.DoesNotExist:
                messages.error(request, "Material not found.")
            except Exception as e:
                messages.error(request, f"Failed to update: {e}")

            return redirect(reverse("app:admin_dashboard") + "?tab=materials")

        if action == "delete_material":
            mat_id = (request.POST.get("mat_id") or "").strip()

            if not mat_id:
                messages.error(request, "Missing material ID.")
                return redirect(reverse("app:admin_dashboard") + "?tab=materials")

            try:
                obj = MaterialList.objects.get(id=mat_id)
                code = obj.mat_partcode
                obj.delete()
                messages.success(request, f"Deleted material: {code}")
            except MaterialList.DoesNotExist:
                messages.error(request, "Material not found.")
            except Exception as e:
                messages.error(request, f"Failed to delete: {e}")

            return redirect(reverse("app:admin_dashboard") + "?tab=materials")

        # -------- USERS actions --------
        if action == "add_employee":
            employee_id = (request.POST.get("employee_id") or "").strip()
            full_name = (request.POST.get("full_name") or "").strip()
            department = (request.POST.get("department") or "").strip()
            password = (request.POST.get("password") or "")

            if not employee_id or not full_name or not department or not password:
                messages.error(request, "All fields are required.")
                return redirect(reverse("app:admin_dashboard") + "?tab=users")

            if User.objects.filter(username=employee_id).exists():
                messages.error(request, f"Employee ID already exists: {employee_id}")
                return redirect(reverse("app:admin_dashboard") + "?tab=users")

            try:
                user = User.objects.create_user(username=employee_id, password=password)
                user.is_staff = True  # you can change this default if you want
                user.save()

                # If you have EmployeeProfile model with OneToOne to User:
                # user.employeeprofile.full_name = full_name ...
                # But since your template uses u.employeeprofile, we create/update safely:
                try:
                    prof = getattr(user, "employeeprofile", None)
                    if prof is None:
                        from .models import EmployeeProfile  # only if your model exists
                        EmployeeProfile.objects.create(user=user, full_name=full_name, department=department)
                    else:
                        prof.full_name = full_name
                        prof.department = department
                        prof.save()
                except Exception:
                    # If your project doesn't have EmployeeProfile model, remove the employeeprofile usage in template
                    pass

                messages.success(request, f"Employee created: {employee_id}")

            except Exception as e:
                messages.error(request, f"Failed to create employee: {e}")

            return redirect(reverse("app:admin_dashboard") + "?tab=users")

        if action == "toggle_user_active":
            user_id = (request.POST.get("user_id") or "").strip()
            if not user_id:
                messages.error(request, "Missing user ID.")
                return redirect(reverse("app:admin_dashboard") + "?tab=users")

            try:
                u = User.objects.get(id=user_id)

                if u.id == request.user.id:
                    messages.error(request, "You can't disable your own account.")
                    return redirect(reverse("app:admin_dashboard") + "?tab=users")

                u.is_active = not u.is_active
                u.save()
                messages.success(request, f"Updated user: {u.username} (active={u.is_active})")
            except User.DoesNotExist:
                messages.error(request, "User not found.")
            except Exception as e:
                messages.error(request, f"Failed to update user: {e}")

            return redirect(reverse("app:admin_dashboard") + "?tab=users")

    # =========================
    # CUSTOMERS TAB DATA
    # =========================
    q = (request.GET.get("q") or "").strip()
    customers = build_customer_table(q)

    # =========================
    # MATERIALS TAB DATA (paginated)
    # =========================
    mq = (request.GET.get("mq") or "").strip()
    materials_qs = MaterialList.objects.all().order_by("mat_partcode")

    if mq:
        materials_qs = materials_qs.filter(
            Q(mat_partcode__icontains=mq) |
            Q(mat_partname__icontains=mq) |
            Q(mat_maker__icontains=mq) |
            Q(unit__icontains=mq)
        )

    paginator = Paginator(materials_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    material_total = materials_qs.count()
    material_list = page_obj

    # =========================
    # USERS TAB DATA (paginated)
    # =========================
    uq = (request.GET.get("uq") or "").strip()
    users_qs = User.objects.all().order_by("-is_superuser", "-is_staff", "username")

    if uq:
        users_qs = users_qs.filter(
            Q(username__icontains=uq) |
            Q(employeeprofile__full_name__icontains=uq) |
            Q(employeeprofile__department__icontains=uq)
        )

    users_paginator = Paginator(users_qs, 10)
    upage = request.GET.get("upage")
    users_page = users_paginator.get_page(upage)
    user_total = users_qs.count()

    # =========================
    # PANEL AJAX REQUEST
    # =========================
    tep_id = request.GET.get("tep_id")
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    if tep_id and is_ajax:
        tep = get_object_or_404(TEPCode.objects.select_related("customer"), id=tep_id)

        materials = Material.objects.filter(tep_code=tep).order_by("mat_partname")

        selected_part = (tep.part_code or "").strip()
        selected_part_name = ""

        for p in (tep.customer.parts or []):
            if isinstance(p, dict) and str(p.get("Partcode", "")).strip() == selected_part:
                selected_part_name = str(p.get("Partname", "")).strip()
                break

        return render(request, "admin/_customer_detail_panel.html", {
            "customer": tep.customer,
            "materials": materials,
            "selected_tep": tep.tep_code,
            "selected_part": selected_part,
            "selected_part_name": selected_part_name,
            "tep_id": tep.id,
        })

    # =========================
    # PAGE CONTEXT
    # =========================
    context = {
        "tab": tab,

        "customers_count": Customer.objects.count(),
        "tep_count": TEPCode.objects.count(),
        "materials_count": Material.objects.count(),
        "users_count": User.objects.count(),

        # customers
        "customers": customers,
        "q": q,

        # materials
        "mq": mq,
        "material_total": material_total,
        "material_list": material_list,
        "page_obj": page_obj,

        # users
        "uq": uq,
        "user_total": user_total,
        "users_page": users_page,
    }
    return render(request, "admin/dashboard.html", context)



@login_required
@user_passes_test(is_admin)
def admin_users(request):
    return redirect(reverse("app:admin_dashboard") + "?tab=users")


@login_required
@user_passes_test(is_admin)
def toggle_user_active(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)

    if user_obj == request.user:
        messages.error(request, "You can't disable your own account.")
        return redirect(reverse("app:admin_dashboard") + "?tab=users")

    user_obj.is_active = not user_obj.is_active
    user_obj.save()

    messages.success(request, f"Updated user: {user_obj.username} (active={user_obj.is_active})")
    return redirect(reverse("app:admin_dashboard") + "?tab=users")


@login_required
@user_passes_test(is_admin)
def create_employee(request):
    if request.method == "POST":
        form = EmployeeCreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Employee account created successfully.")
            return redirect(reverse("app:admin_dashboard") + "?tab=users")
    else:
        form = EmployeeCreateForm()

    return render(request, "create_employee.html", {"form": form})


@login_required
@user_passes_test(is_admin)
def admin_csv_upload(request):
    default_next = reverse("app:admin_dashboard") + "?tab=materials"
    next_url = request.POST.get("next") or request.GET.get("next") or default_next

    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = default_next

    if request.method == "POST" and request.FILES.get("csv_file"):
        f = request.FILES["csv_file"]
        raw = f.read()

        content = None
        for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
            try:
                content = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            messages.error(request, "Could not read file encoding. Save as CSV UTF-8 and upload again.")
            return redirect(next_url)

        csv_file = io.StringIO(content)
        reader = csv.DictReader(csv_file)
        reader.fieldnames = [h.strip().lstrip("\ufeff") for h in (reader.fieldnames or [])]

        master_inserted = 0
        master_updated = 0
        ALLOWED_UNITS = {"pc", "pcs", "m"}

        def sget(row, *keys, default=""):
            for k in keys:
                v = row.get(k)
                if v is not None and str(v).strip() != "":
                    return str(v).strip()
            return default

        try:
            with transaction.atomic():
                for row in reader:
                    mat_partcode = sget(row, "mat_partcode", "material_part_code")
                    mat_partname = sget(row, "mat_partname", "material_name")
                    mat_maker = sget(row, "mat_maker", "maker")
                    unit = sget(row, "unit", default="pc").lower()

                    if unit not in ALLOWED_UNITS:
                        unit = "pc"

                    if not mat_partcode:
                        continue

                    master, created_master = MaterialList.objects.get_or_create(
                        mat_partcode=mat_partcode,
                        defaults={
                            "mat_partname": mat_partname or mat_partcode,
                            "mat_maker": mat_maker or "Unknown",
                            "unit": unit,
                        }
                    )

                    if created_master:
                        master_inserted += 1
                    else:
                        changed = False
                        if mat_partname and master.mat_partname != mat_partname:
                            master.mat_partname = mat_partname
                            changed = True
                        if mat_maker and master.mat_maker != mat_maker:
                            master.mat_maker = mat_maker
                            changed = True
                        if unit and master.unit != unit:
                            master.unit = unit
                            changed = True
                        if changed:
                            master.save()
                            master_updated += 1

            messages.success(
                request,
                f"CSV uploaded successfully | master_inserted={master_inserted}, master_updated={master_updated}"
            )
            return redirect(next_url)

        except Exception as e:
            messages.error(request, f"Upload failed: {e}")
            return redirect(next_url)

    return redirect(next_url)


@login_required
def customer_list(request):
    q = (request.GET.get("q") or "").strip()
    customers = build_customer_table(q)
    return render(request, "customer_list.html", {"customers": customers, "q": q})


@login_required
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

    selected_part = (tep.part_code or "").strip()
    selected_part_name = ""

    for p in (tep.customer.parts or []):
        if isinstance(p, dict) and str(p.get("Partcode", "")).strip() == selected_part:
            selected_part_name = str(p.get("Partname", "")).strip()
            break

    return render(request, "customer_detail.html", {
        "customer": tep.customer,
        "materials": materials,
        "selected_tep": tep.tep_code,
        "selected_part": selected_part,
        "selected_part_name": selected_part_name,
        "tep_id": tep.id,
    })
