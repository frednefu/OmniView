"""信息系统管理 API — CRUD + 导入导出。"""
import io, uuid, time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import openpyxl

from app.database import get_db
from app.models.info_system import InfoSystem, DjDjRecord, IcpRecord, SupplyChain
from app.models.user import User
from app.models.department import Department
from app.utils.security import hash_password
from app.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/info-systems", tags=["信息系统"])


_asset_id_counter = 0

def _gen_asset_id(db: Session = None) -> str:
    """生成唯一资产ID，重试直到不冲突。"""
    global _asset_id_counter
    for _ in range(100):
        _asset_id_counter += 1
        ts = datetime.now().strftime('%Y%m%d%H%M%S')
        aid = f"IS-{ts}-{uuid.uuid4().hex[:8]}-{_asset_id_counter:04d}"
        if db is None:
            return aid
        if not db.query(InfoSystem).filter(InfoSystem.asset_id == aid).first():
            return aid
    raise HTTPException(500, "无法生成唯一资产ID")


# ── 人员查询 + 自动注册 ──

@router.get("/staff-search")
def search_staff(q: str = Query("", min_length=1), db: Session = Depends(get_db), _=Depends(require_admin)):
    """按姓名或工号搜索系统用户，未找到则返回空。"""
    items = db.query(User).filter(
        (User.name.contains(q)) | (User.gh.contains(q)) | (User.username.contains(q))
    ).limit(15).all()
    return {"items": [{"id": u.id, "name": u.name, "gh": u.gh, "username": u.username,
                        "phone": u.phone, "mobile": u.mobile, "department_name": u.department.dwmc if u.department else ""} for u in items]}


@router.get("/staff-lookup")
def lookup_staff(q: str = Query("", min_length=1), db: Session = Depends(get_db), _=Depends(require_admin)):
    """查找人员（系统用户 + 教职工库），返回合并结果供确认。"""
    results = []
    # 1. 系统用户
    users = db.query(User).filter(
        (User.name.contains(q)) | (User.gh.contains(q)) | (User.username.contains(q))
    ).limit(10).all()
    for u in users:
        results.append({"id": u.id, "name": u.name, "gh": u.gh, "username": u.username,
                        "phone": u.phone, "mobile": u.mobile,
                        "department_name": u.department.dwmc if u.department else "",
                        "source": "系统用户"})
    # 2. 教职工库（排除已有用户）
    from app.models.staff_info import StaffInfo
    existing_ghs = {u.gh for u in users if u.gh}
    staffs = db.query(StaffInfo).filter(
        (StaffInfo.xm.contains(q)) | (StaffInfo.gh.contains(q))
    ).limit(10).all()
    for s in staffs:
        if s.gh and s.gh in existing_ghs:
            continue
        results.append({"id": None, "name": s.xm, "gh": s.gh, "username": None,
                        "phone": s.bgdh or "", "mobile": s.yddh or "",
                        "department_name": s.szdwbm or "",
                        "source": "教职工库（可注册）"})
    return {"items": results[:15]}


@router.post("/staff-register")
def register_staff(body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    """查询教职工并自动注册为系统用户（如不存在）。返回用户信息。"""
    name = (body.get("name") or "").strip()
    gh = (body.get("gh") or "").strip()
    if not name and not gh:
        raise HTTPException(400, "请提供姓名或工号")
    # 先在本地查找
    q = db.query(User)
    if name and gh:
        q = q.filter(User.name == name, User.gh == gh)
    elif gh:
        q = q.filter(User.gh == gh)
    elif name:
        q = q.filter(User.name == name)
    user = q.first()
    if user:
        return {"id": user.id, "name": user.name, "gh": user.gh, "username": user.username,
                "phone": user.phone, "mobile": user.mobile, "department_name": user.department.dwmc if user.department else "",
                "existed": True}
    # 尝试从 staff_info 查找
    from app.models.staff_info import StaffInfo
    sq = db.query(StaffInfo)
    if name and gh:
        sq = sq.filter(StaffInfo.xm == name, StaffInfo.gh == gh)
    elif gh:
        sq = sq.filter(StaffInfo.gh == gh)
    elif name:
        sq = sq.filter(StaffInfo.xm == name)
    staff = sq.first()
    if staff:
        username = staff.gh or f"u{int(time.time())}"
        exist = db.query(User).filter(User.username == username).first()
        if exist:
            username = f"{staff.gh}_{int(time.time() % 1000)}"
        # 尝试根据部门编码匹配部门
        dept_id = None
        if staff.szdwbm:
            d = db.query(Department).filter(Department.dwbm == staff.szdwbm).first()
            if d:
                dept_id = d.id
        new_user = User(
            username=username,
            password_hash=hash_password("Abcd1234!"),
            name=staff.xm,
            gh=staff.gh,
            gender="男" if staff.xbm == "1" else ("女" if staff.xbm == "2" else ""),
            phone=staff.bgdh or "",
            mobile=staff.yddh or "",
            email=staff.dzyx or "",
            department_id=dept_id,
            user_type="internal",
            role="user",
            is_active=True,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"id": new_user.id, "name": new_user.name, "gh": new_user.gh, "username": new_user.username,
                "phone": new_user.phone, "mobile": new_user.mobile, "department_name": new_user.department.dwmc if new_user.department else "",
                "existed": False, "message": f"已从教职工库自动注册用户: {new_user.name}"}
    raise HTTPException(404, "未找到匹配的教职工信息")


# ── InfoSystem CRUD ──

@router.get("")
def list_systems(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                 search: str = Query(""), fill_type: str = Query(""),
                 db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(InfoSystem)
    if search:
        kw = f"%{search}%"
        q = q.filter(InfoSystem.system_name.like(kw) | InfoSystem.ip_address.like(kw) | InfoSystem.domain.like(kw))
    if fill_type:
        q = q.filter(InfoSystem.fill_type == fill_type)
    total = q.count()
    items = q.order_by(InfoSystem.id).offset((page - 1) * size).limit(size).all()
    return {"items": [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in items], "total": total}


@router.post("/batch-delete")
def batch_delete_systems(body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(400, "请选择记录")
    db.query(InfoSystem).filter(InfoSystem.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"message": f"已删除 {len(ids)} 条"}


def _clean_empty_dates(data: dict) -> dict:
    """将 Date 类型字段的空字符串转为 None，避免 MySQL 1292 错误。"""
    from sqlalchemy import Date
    date_cols = {c.name for c in InfoSystem.__table__.columns if isinstance(c.type, Date)}
    for k, v in data.items():
        if k in date_cols and v == "":
            data[k] = None
    return data


@router.post("")
def create_system(body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not body.get("asset_id"):
        body["asset_id"] = _gen_asset_id(db)
    if db.query(InfoSystem).filter(InfoSystem.asset_id == body["asset_id"]).first():
        raise HTTPException(400, "资产ID已存在")
    valid_cols = {c.name for c in InfoSystem.__table__.columns}
    sys = InfoSystem(**_clean_empty_dates({k: v for k, v in body.items() if k in valid_cols and k != 'id'}))
    try:
        db.add(sys); db.commit(); db.refresh(sys)
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"创建失败：{e}")
    return {"id": sys.id, "message": "已创建"}


@router.put("/{sys_id}")
def update_system(sys_id: int, body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    sys = db.query(InfoSystem).get(sys_id)
    if not sys: raise HTTPException(404, "不存在")
    valid_cols = {c.name for c in sys.__table__.columns}
    body = _clean_empty_dates(body)
    for k, v in body.items():
        if k != "id" and k in valid_cols:
            setattr(sys, k, v)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"保存失败：{e}")
    return {"message": "已更新"}


@router.delete("/{sys_id}")
def delete_system(sys_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    db.query(InfoSystem).filter(InfoSystem.id == sys_id).delete()
    db.commit()
    return {"message": "已删除"}


# ── Excel 导入 ──

# ── 导入格式定义 ──

def _detect_import_format(ws) -> str:
    """检测 Excel 文件格式，返回格式名称。"""
    # 读取前两行的列值
    row1 = [_cell_str(ws.cell(1, c).value) for c in range(1, min(ws.max_column + 1, 80))]
    row2 = [_cell_str(ws.cell(2, c).value) for c in range(1, min(ws.max_column + 1, 80))]
    r1 = " ".join(row1)
    r2 = " ".join(row2)
    # 格式1: 信息系统管理_*.xlsx（行1是中文表头，含"单位名称"+"管理员姓名"）
    if "单位名称" in r1 and "管理员姓名" in r1:
        return "iso_report"
    # 格式2: 资产清单.xlsx（行1是说明文字，行2是"ID"+"所属单位"+"信息系统名称"等表头）
    if ("说明" in r1 or "必填" in r1 or len(row1[0]) > 50) and "ID" in row2 and "所属单位" in r2:
        return "asset_list"
    # 格式3: 资产导出.xlsx（行1是长说明，行2直接是数据或无表头行）
    if "填写说明" in r1 or "必填项" in r1 or len(row1[0]) > 50:
        return "asset_export"
    return "unknown"


# 旧格式（资产导出.xlsx）列映射：列号 → (模型字段, 转换函数或None)
_FORMAT_ASSET_EXPORT = {
    3:  "system_name",
    4:  "system_type",
    5:  "sub_type",
    6:  "ip_address",
    7:  "domain",
    8:  "djdj_status",
    12: "djdj_sys_name",
    13: "djdj_date",
    14: "djdj_no",
    2:  "org_name",
    25: "dept_name",
    27: "contact",
    28: "contact_phone",
    11: "remark",
}

# 新格式（信息系统管理_*.xlsx）列映射：列号 → (模型字段, 转换函数或None)
_FORMAT_ISO_REPORT = {
    3:  "org_name",           # 单位名称
    4:  "_dept_code",         # 单位名称_代码 → 查 departments.dwbm 得到 dept_id
    5:  "manager_name",       # 管理员姓名
    6:  "manager_gh",         # 管理员工号_账号 → 无账号则自动创建
    8:  "_manager_mobile",    # 管理员手机号码 → 创建账号时填入 mobile
    10: "system_type",        # 系统类型
    11: "sub_type",           # 信息系统类型 (K列，主键)
    12: "product_name",       # 产品名称
    13: "product_version",    # 版本号
    14: "domain",             # 域名
    15: "ip_address",         # 业务互联网IP
    16: "ip_address2",        # 业务内网IP（合并到ip_address）
    18: "dept_name",          # 运维单位
    24: "source_type",        # 数据来源
    41: "djdj_status",        # 等保定级情况
    42: "djdj_sys_name",      # 等保二级系统名称 → 等保信息维护表联动
    43: "djdj_no",            # 等保定级编号
    44: "djdj_date",          # 等保定级时间
    47: "icp_no",             # ICP备案号
    49: "icp_date",           # ICP备案时间
    51: "remark",             # 备注
    52: "vendor_name",        # 供应链单位名称 → 供应链信息维护表联动
    56: "vendor_contact",     # 供应链联系人
    57: "vendor_phone",       # 供应链联系电话
    70: "submitter",          # 提交人
}


def _parse_excel_date(val):
    """尝试将值解析为日期字符串。"""
    if val is None: return None
    if isinstance(val, (datetime,)): return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if not s: return None
    # 尝试常见日期格式
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S"]:
        try:
            datetime.strptime(s[:19] if len(s) > 19 else s, fmt)
            return s[:10]
        except ValueError:
            continue
    return s[:10] if len(s) >= 10 else None


def _is_empty(val) -> bool:
    """判断值是否为空。"""
    if val is None: return True
    if isinstance(val, str) and not val.strip(): return True
    return False


def _parse_row_asset_export(ws, row_idx: int) -> dict:
    """解析旧格式的一行数据。"""
    data = {"fill_type": "导入"}
    for col, field in _FORMAT_ASSET_EXPORT.items():
        raw = ws.cell(row_idx, col).value
        if field == "djdj_date":
            data[field] = _parse_excel_date(raw)
        else:
            data[field] = _cell_str(raw)
    # 合并内网IP（如果有第16列）
    ip2 = _cell_str(ws.cell(row_idx, 16).value)
    if ip2 and data.get("ip_address"):
        data["ip_address"] = data["ip_address"] + ("," if not data["ip_address"].endswith(",") else "") + ip2
    elif ip2:
        data["ip_address"] = ip2
    return data


# 资产清单.xlsx 格式：表头名 → 模型字段
_FORMAT_ASSET_LIST_HEADER_MAP = {
    "所属单位":              "org_name",
    "信息系统名称":          "system_name",
    "资产类型":              "system_type",
    "信息系统类型":          "sub_type",
    "IP":                   "ip_address",
    "域名":                 "domain",
    "等保备案级别":          "djdj_level",
    "备注":                 "remark",
    "等保备案系统名称":      "djdj_sys_name",
    "等保备案时间":          "djdj_date",
    "等保备案编号":          "djdj_no",
    "联系人":               "contact",
    "联系人电话":           "contact_phone",
    "系统运维单位":          "dept_name",
    "内网URL":              "internal_url",
    "内网IP地址段（只明确到C段）": "ip_range",
    # 供应链第1组
    "供应链厂商情况-开发厂商名称-1": "vendor_name",
    "供应链厂商情况-产品名称-1":   "product_name",
    "供应链厂商情况-版本号-1":     "product_version",
    "供应链厂商情况-来源-1":       "source_type",
    # 供应链第2组
    "供应链厂商情况-开发厂商名称-2": "_vendor2_name",
    "供应链厂商情况-产品名称-2":   "_vendor2_product",
    "供应链厂商情况-版本号-2":     "_vendor2_version",
    "供应链厂商情况-来源-2":       "_vendor2_source",
}
# 资产清单中需要合并到 ip_address 的额外列
_ASSET_LIST_EXTRA_IP_HEADERS = ["互联网接入IP地址", "IP"]


def _build_asset_list_col_map(ws) -> dict:
    """从第2行表头构建 列号→模型字段 的映射。"""
    col_map = {}
    for c in range(1, ws.max_column + 1):
        header = _cell_str(ws.cell(2, c).value).strip()
        if header in _FORMAT_ASSET_LIST_HEADER_MAP:
            col_map[c] = _FORMAT_ASSET_LIST_HEADER_MAP[header]
    return col_map


def _parse_row_asset_list(ws, row_idx: int, col_map: dict) -> dict:
    """解析资产清单.xlsx 的一行数据。"""
    data = {"fill_type": "导入"}
    ip_parts = []
    for c in range(1, ws.max_column + 1):
        raw = ws.cell(row_idx, c).value
        val_str = _cell_str(raw)
        header = _cell_str(ws.cell(2, c).value).strip()
        # 收集所有 IP 列（主IP + 内部IP等）
        if header in _ASSET_LIST_EXTRA_IP_HEADERS and val_str:
            ip_parts.append(val_str)
        if c in col_map:
            field = col_map[c]
            if field == "djdj_date":
                data[field] = _parse_excel_date(raw)
            else:
                data[field] = val_str
    # 合并 IP
    if ip_parts:
        data["ip_address"] = ",".join(dict.fromkeys(ip_parts))  # 去重保序
    return data


def _parse_row_iso_report(ws, row_idx: int) -> dict:
    """解析新格式的一行数据。"""
    data = {"fill_type": "导入"}
    for col, field in _FORMAT_ISO_REPORT.items():
        raw = ws.cell(row_idx, col).value
        if field in ("djdj_date", "icp_date"):
            data[field] = _parse_excel_date(raw)
        elif field == "ip_address2":
            data["_ip_internal"] = _cell_str(raw)
        elif field == "_dept_code":
            data["_dept_code"] = _cell_str(raw)
        elif field == "_manager_mobile":
            data["_manager_mobile"] = _cell_str(raw)
        elif field == "submitter":
            data["contact"] = _cell_str(raw)
        else:
            data[field] = _cell_str(raw)
    # 提取系统名称（主键：K列=信息系统类型 → 产品名称 → 系统类型）
    system_name = data.get("sub_type", "") or data.get("product_name", "") or data.get("system_type", "")
    data["system_name"] = system_name
    # 合并IP
    ip_ext = data.get("ip_address", "")
    ip_int = data.pop("_ip_internal", "")
    if ip_int:
        data["ip_address"] = (ip_ext + ("," if ip_ext and not ip_ext.endswith(",") else "") + ip_int) if ip_ext else ip_int
    return data


# ── 导入端点 ──

@router.post("/import")
def import_excel(file: UploadFile, mode: str = Query("supplement"),
                 db: Session = Depends(get_db), _=Depends(require_admin)):
    """
    导入 Excel 文件，自动识别格式。
    mode: overwrite=覆盖已有 / supplement=补充空白字段 / skip=跳过重复
    """
    if mode not in ("overwrite", "supplement", "skip"):
        raise HTTPException(400, "mode 必须是 overwrite / supplement / skip 之一")
    try:
        return _do_import(file, mode, db)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(500, f"导入失败：{e}\n{traceback.format_exc()}")


def _do_import(file: UploadFile, mode: str, db: Session):
    wb = openpyxl.load_workbook(io.BytesIO(file.file.read()))
    ws = wb.active

    # 检测格式
    fmt = _detect_import_format(ws)
    if fmt == "unknown":
        raise HTTPException(400, "无法识别文件格式，请确认文件类型。支持：资产导出.xlsx、信息系统管理_*.xlsx")

    # 找到数据起始行
    if fmt == "asset_export":
        start_row = _find_data_start(ws)
        parse_row = _parse_row_asset_export
        fmt_name = "资产导出"
    elif fmt == "asset_list":
        start_row = 3  # 行1=说明, 行2=表头, 行3起=数据
        col_map = _build_asset_list_col_map(ws)
        parse_row = lambda ws, ri: _parse_row_asset_list(ws, ri, col_map)
        fmt_name = "资产清单"
    else:
        start_row = 2  # 第1行是表头，第2行开始是数据
        parse_row = _parse_row_iso_report
        fmt_name = "信息系统管理"

    # 解析所有行
    parsed = []
    system_names_seen = set()
    for row_idx in range(start_row, ws.max_row + 1):
        row_data = parse_row(ws, row_idx)
        sn = row_data.get("system_name", "").strip()
        if not sn:
            continue
        # Excel 内重复的系统名称只取第一次
        if sn in system_names_seen:
            continue
        system_names_seen.add(sn)
        parsed.append(row_data)

    # 统计 + 导入
    stats = {"total": len(parsed), "created": 0, "updated": 0, "supplemented": 0, "skipped": 0, "errors": 0,
             "dept_matched": 0, "users_created": 0, "supply_added": 0, "format": fmt_name}
    # 预加载已有供应链公司名
    existing_companies = {c[0] for c in db.query(SupplyChain.company_name).all()}
    valid_cols = {c.name for c in InfoSystem.__table__.columns}
    date_cols = {"djdj_date", "icp_date"}

    # 清理存量数据中前后带空格的系统名称
    try:
        dirty = db.query(InfoSystem).filter(
            (InfoSystem.system_name.startswith(" ")) | (InfoSystem.system_name.endswith(" "))
        ).all()
        for d in dirty:
            d.system_name = d.system_name.strip()
        if dirty:
            db.flush()
    except Exception:
        pass

    # 预加载部门代码映射（仅新格式需要）
    dept_code_map = {}
    if fmt == "iso_report":
        depts = db.query(Department).filter(Department.dwbm.isnot(None)).all()
        dept_code_map = {d.dwbm: d.id for d in depts if d.dwbm}

    # 预加载已有的用户工号
    existing_ghs = {u.gh for u in db.query(User).filter(User.gh.isnot(None), User.gh != "").all()}

    # 收集需要创建账号的管理员工号 → 通过外部 API 获取详细信息
    staff_cache = {}  # gh → staff_dict (来自 fetch_staff API)
    if fmt == "iso_report":
        new_manager_ghs = []
        for row_data in parsed:
            gh = row_data.get("manager_gh", "").strip()
            name = row_data.get("manager_name", "").strip()
            if gh and name and gh not in existing_ghs:
                new_manager_ghs.append(gh)
        new_manager_ghs = list(dict.fromkeys(new_manager_ghs))  # 去重保序

        if new_manager_ghs:
            try:
                from app.services.external_api_service import fetch_staff
                for gh in new_manager_ghs:
                    try:
                        results = fetch_staff(db, gh=gh)
                        if results:
                            # 优先取工号完全匹配的第一条
                            staff_cache[gh] = results[0]
                    except Exception:
                        pass  # API 不可用时跳过
            except Exception:
                pass  # 外部 API 模块不可用时跳过

    for row_data in parsed:
        try:
            system_name = row_data["system_name"].strip()
            row_data["system_name"] = system_name  # 确保写入DB的名称已去空格

            # 解析部门代码 → dept_id
            dept_code = row_data.pop("_dept_code", "")
            if dept_code and dept_code in dept_code_map:
                row_data["dept_id"] = dept_code_map[dept_code]
                stats["dept_matched"] += 1
            # 清理内部字段
            manager_mobile = row_data.pop("_manager_mobile", "")

            # 管理员自动创建账号（参考 asset_match.py 的 fetch_staff 逻辑）
            manager_gh = row_data.get("manager_gh", "").strip()
            manager_name = row_data.get("manager_name", "").strip()
            if manager_gh and manager_name and manager_gh not in existing_ghs:
                staff = staff_cache.get(manager_gh, {})
                staff_dept_code = (staff.get("SZDWBM") or "").strip()
                staff_dept_id = dept_code_map.get(staff_dept_code) if staff_dept_code else None
                email = (staff.get("DZYX") or "").strip() or None
                phone = (staff.get("BGDH") or "").strip() or None
                mobile = manager_mobile or (staff.get("YDDH") or "").strip() or None
                gender = "男" if staff.get("XBM") == "1" else "女" if staff.get("XBM") == "2" else ""
                # 检查 email 是否已被其他用户占用
                if email:
                    email_taken = db.query(User).filter(User.email == email, User.gh != manager_gh).first()
                    if email_taken:
                        email = None
                try:
                    new_user = User(
                        username=manager_gh,
                        gh=manager_gh,
                        name=manager_name,
                        user_type="internal",
                        password_hash=hash_password("Abcd1234!"),
                        email=email,
                        phone=phone,
                        mobile=mobile,
                        gender=gender,
                        department_id=staff_dept_id or (dept_code_map.get(dept_code) if dept_code else None),
                    )
                    db.add(new_user)
                    db.flush()
                    existing_ghs.add(manager_gh)
                    stats["users_created"] += 1
                except Exception:
                    db.rollback()  # 重置会话状态
                    # 重试：不带 email（可能是其它约束冲突）
                    try:
                        new_user2 = User(
                            username=manager_gh,
                            gh=manager_gh,
                            name=manager_name,
                            user_type="internal",
                            password_hash=hash_password("Abcd1234!"),
                            phone=phone,
                            mobile=mobile,
                            gender=gender,
                            department_id=staff_dept_id or (dept_code_map.get(dept_code) if dept_code else None),
                        )
                        db.add(new_user2)
                        db.flush()
                        existing_ghs.add(manager_gh)
                        stats["users_created"] += 1
                    except Exception:
                        db.rollback()

            existing = db.query(InfoSystem).filter(InfoSystem.system_name == system_name).first()

            if existing:
                if mode == "skip":
                    stats["skipped"] += 1
                    continue
                elif mode == "overwrite":
                    for k, v in row_data.items():
                        if k != "id" and k in valid_cols:
                            if k in date_cols and _is_empty(v):
                                setattr(existing, k, None)
                            else:
                                setattr(existing, k, v)
                    existing.fill_type = "导入"
                    stats["updated"] += 1
                elif mode == "supplement":
                    changed = False
                    for k, v in row_data.items():
                        if k != "id" and k in valid_cols:
                            current = getattr(existing, k, None)
                            if _is_empty(current) and not _is_empty(v):
                                if k in date_cols:
                                    setattr(existing, k, _parse_excel_date(v))
                                else:
                                    setattr(existing, k, v)
                                changed = True
                    if changed:
                        stats["supplemented"] += 1
                    else:
                        stats["skipped"] += 1
            else:
                clean = {}
                for k, v in row_data.items():
                    if k in valid_cols:
                        if k in date_cols and _is_empty(v):
                            clean[k] = None
                        else:
                            clean[k] = v
                clean["asset_id"] = _gen_asset_id(db)
                sys_obj = InfoSystem(**clean)
                db.add(sys_obj)
                stats["created"] += 1

            # 供应链自动入库：开发厂商名称不在 supply_chains 表中则自动添加
            vendor = (row_data.get("vendor_name") or "").strip()
            if vendor and vendor not in existing_companies:
                try:
                    sc = SupplyChain(company_name=vendor)
                    db.add(sc)
                    db.flush()
                    existing_companies.add(vendor)
                    stats["supply_added"] += 1
                except Exception:
                    db.rollback()

            # 第2组供应链厂商 → 拼接到备注
            v2_name = row_data.pop("_vendor2_name", "")
            if v2_name and v2_name.strip():
                parts = [v2_name.strip()]
                for k2 in ("_vendor2_product", "_vendor2_version", "_vendor2_source"):
                    v2 = row_data.pop(k2, "")
                    if v2 and v2.strip():
                        parts.append(v2.strip())
                v2_text = " / ".join(parts)
                existing_remark = row_data.get("remark", "") or (getattr(existing, "remark", None) if existing else "")
                if existing_remark:
                    row_data["remark"] = str(existing_remark) + " | 供应商2: " + v2_text
                else:
                    row_data["remark"] = "供应商2: " + v2_text
            else:
                for k2 in ("_vendor2_name", "_vendor2_product", "_vendor2_version", "_vendor2_source"):
                    row_data.pop(k2, None)

        except Exception:
            db.rollback()
            stats["errors"] += 1

    db.commit()
    parts = [f"导入完成（{fmt_name}格式）：共 {stats['total']} 条"]
    if stats['created']: parts.append(f"新建 {stats['created']}")
    if stats['updated']: parts.append(f"覆盖 {stats['updated']}")
    if stats['supplemented']: parts.append(f"补充 {stats['supplemented']}")
    if stats['skipped']: parts.append(f"跳过 {stats['skipped']}")
    if stats['errors']: parts.append(f"失败 {stats['errors']}")
    if stats['dept_matched']: parts.append(f"匹配部门 {stats['dept_matched']}")
    if stats['users_created']: parts.append(f"创建账号 {stats['users_created']}")
    if stats['supply_added']: parts.append(f"新增供应链 {stats['supply_added']}")
    stats["message"] = "，".join(parts)
    return stats


# ── Excel 导出 ──

@router.get("/export")
def export_excel(db: Session = Depends(get_db), _=Depends(require_admin)):
    items = db.query(InfoSystem).order_by(InfoSystem.id).all()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "信息系统"
    # 中文表头映射（按逻辑分组排序）
    export_cols = [
        ("asset_id", "资产ID"),
        ("system_name", "系统名称"),
        ("system_type", "资产类型"),
        ("sub_type", "信息系统类型"),
        ("ip_address", "IP地址"),
        ("domain", "域名/URL"),
        ("org_name", "单位名称"),
        ("dept_name", "运维单位"),
        ("contact", "联系人"),
        ("contact_phone", "联系电话"),
        ("fill_type", "填报类型"),
        # 归属信息
        ("dept_id", "所属部门ID"),
        ("manager_name", "管理员姓名"),
        ("manager_gh", "管理员工号"),
        ("owner_name", "负责人姓名"),
        ("owner_gh", "负责人工号"),
        # 等级保护
        ("djdj_status", "等保状态"),
        ("djdj_sys_name", "等保系统名称"),
        ("djdj_no", "等保编号"),
        ("djdj_level", "等保等级"),
        ("djdj_date", "等保日期"),
        ("djdj_org", "测评单位"),
        # ICP
        ("icp_no", "ICP备案号"),
        ("icp_date", "ICP备案日期"),
        # 供应链
        ("vendor_name", "开发厂商"),
        ("product_name", "产品名称"),
        ("product_version", "版本号"),
        ("source_type", "来源"),
        ("vendor_contact", "厂商联系人"),
        ("vendor_phone", "厂商电话"),
        ("ops_contact", "运维联系人"),
        ("ops_phone", "运维电话"),
        # 其他
        ("has_website", "是否有网站"),
        ("internal_url", "内网URL"),
        ("ip_range", "IP地址段"),
        ("remark", "备注"),
    ]
    headers = [h for _, h in export_cols]
    fields = [f for f, _ in export_cols]
    ws.append(headers)
    date_fmt_cols = {"djdj_date", "icp_date"}
    for r in items:
        row = []
        for f in fields:
            v = getattr(r, f, None)
            if v is None:
                row.append("")
            elif f in date_fmt_cols and hasattr(v, "strftime"):
                row.append(v.strftime("%Y-%m-%d"))
            else:
                row.append(v)
        ws.append(row)
    # 自动调整列宽
    for col_idx in range(1, len(headers) + 1):
        max_len = min(len(str(headers[col_idx - 1])) * 2, 30)
        for row_idx in range(2, min(ws.max_row + 1, 30)):
            cv = str(ws.cell(row_idx, col_idx).value or "")
            clen = sum(2 if ord(c) > 127 else 1 for c in cv)
            if clen > max_len:
                max_len = clen
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = min(max_len + 2, 50)
    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": "attachment; filename=info_systems.xlsx"})


# ── 等保记录 CRUD ──

@router.get("/djdj/image/{rec_id}")
def get_djdj_image(rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(DjDjRecord).get(rec_id)
    if not rec or not rec.image_path:
        raise HTTPException(404, "无图片")
    filepath = f"uploads/{rec.image_path}"
    if not os.path.exists(filepath):
        raise HTTPException(404, "文件不存在")
    return FileResponse(filepath)


@router.get("/djdj")
def list_djdj(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
              search: str = Query(""), db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(DjDjRecord)
    if search:
        q = q.filter(DjDjRecord.system_name.like(f"%{search}%") | DjDjRecord.record_no.like(f"%{search}%"))
    total = q.count()
    items = q.order_by(DjDjRecord.id).offset((page - 1) * size).limit(size).all()
    result = []
    for r in items:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        result.append(d)
    return {"items": result, "total": total}

@router.post("/djdj")
def create_djdj(body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    data = dict(body)
    # 兼容旧字段名 dept_name → eval_org
    if "dept_name" in data and "eval_org" not in data:
        data["eval_org"] = data.pop("dept_name")
    elif "dept_name" in data:
        data.pop("dept_name")
    rec = DjDjRecord(**{k: v for k, v in data.items() if hasattr(DjDjRecord, k)})
    db.add(rec); db.commit(); db.refresh(rec)
    return {"id": rec.id, "message": "已创建"}

@router.put("/djdj/{rec_id}")
def update_djdj(rec_id: int, body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    rec = db.query(DjDjRecord).get(rec_id)
    if not rec: raise HTTPException(404, "不存在")
    data = dict(body)
    if "dept_name" in data and "eval_org" not in data:
        data["eval_org"] = data.pop("dept_name")
    elif "dept_name" in data:
        data.pop("dept_name")
    for k, v in data.items():
        if hasattr(rec, k) and k != "id": setattr(rec, k, v)
    db.commit()
    return {"message": "已更新"}

@router.delete("/djdj/{rec_id}")
def delete_djdj(rec_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    db.query(DjDjRecord).filter(DjDjRecord.id == rec_id).delete()
    db.commit()
    return {"message": "已删除"}

@router.post("/djdj/batch-delete")
def batch_delete_djdj(body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    ids = body.get("ids", [])
    if not ids: raise HTTPException(400, "请选择记录")
    db.query(DjDjRecord).filter(DjDjRecord.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"message": f"已删除 {len(ids)} 条"}

@router.post("/djdj/upload-image/{rec_id}")
def upload_djdj_image(rec_id: int, file: UploadFile, db: Session = Depends(get_db), _=Depends(require_admin)):
    rec = db.query(DjDjRecord).get(rec_id)
    if not rec: raise HTTPException(404, "不存在")
    import os, shutil
    upload_dir = "uploads/djdj"
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or ".jpg")[1] or ".jpg"
    name = f"{rec_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = f"{upload_dir}/{name}"
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    rec.image_path = f"djdj/{name}"
    db.commit()
    return {"message": "已上传", "image_path": rec.image_path}

@router.delete("/djdj/delete-image/{rec_id}")
def delete_djdj_image(rec_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    rec = db.query(DjDjRecord).get(rec_id)
    if not rec: raise HTTPException(404, "不存在")
    if rec.image_path:
        import os
        filepath = f"uploads/{rec.image_path}"
        if os.path.exists(filepath):
            os.remove(filepath)
    rec.image_path = None
    db.commit()
    return {"message": "图片已删除"}

from datetime import date as date_type

def _find_data_start(ws):
    """跳过说明行和表头行，找到数据起始行。"""
    for row_idx in range(1, min(ws.max_row + 1, 10)):
        val = ws.cell(row=row_idx, column=1).value
        if val is not None:
            s = str(val).strip()
            if s.isdigit() and len(s) >= 4:
                return row_idx
    return 3

def _cell_str(val) -> str:
    """安全转换单元格值为字符串。"""
    if val is None: return ""
    if isinstance(val, (int, float)): return str(int(val))
    if isinstance(val, date_type): return val.strftime("%Y-%m-%d")
    return str(val)


@router.post("/djdj/import")
def import_djdj(file: UploadFile, db: Session = Depends(get_db), _=Depends(require_admin)):
    try:
        data = file.file.read()
        wb = openpyxl.load_workbook(io.BytesIO(data))
        ws = wb.active
        imported = 0
        skipped = 0
        dupes = []
        for row in ws.iter_rows(min_row=3, values_only=True):
            vals = [_cell_str(v) for v in row]
            org = vals[1] if len(vals) > 1 else ""
            level = vals[2] if len(vals) > 2 else ""
            sys_name = vals[3] if len(vals) > 3 else ""
            rn = vals[4] if len(vals) > 4 else ""
            rd = vals[5] if len(vals) > 5 and vals[5] else None
            if not rn or not sys_name:
                continue
            exist = db.execute(text("SELECT id,system_name,org_name FROM djdj_records WHERE record_no=:r"), {"r": rn}).fetchone()
            if exist:
                skipped += 1
                dupes.append({"备案编号": rn, "导入系统名": sys_name, "已存在系统名": exist.system_name, "导入单位": org, "已存在单位": exist.org_name})
                continue
            db.add(DjDjRecord(record_no=rn, system_name=sys_name, org_name=org, level=level, record_date=rd))
            db.flush()
            imported += 1
        db.commit()
        return {"message": f"导入完成：新增 {imported} 条，跳过重复 {skipped} 条", "duplicates": dupes[:20]}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"导入失败：{e}")

@router.get("/djdj/export")
def export_djdj(db: Session = Depends(get_db), _=Depends(require_admin)):
    items = db.query(DjDjRecord).all()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "等保备案"
    ws.append(["备案编号", "系统名称", "备案单位", "等级", "备案日期", "测评单位"])
    for r in items:
        ws.append([r.record_no, r.system_name, r.org_name, r.level,
                    str(r.record_date) if r.record_date else "", r.eval_org])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=djdj_export.xlsx"})


# ── ICP记录 CRUD ──

@router.get("/icp")
def list_icp(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
             search: str = Query(""), db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(IcpRecord)
    if search:
        q = q.filter(IcpRecord.icp_no.like(f"%{search}%") | IcpRecord.org_name.like(f"%{search}%"))
    total = q.count()
    items = q.order_by(IcpRecord.id).offset((page - 1) * size).limit(size).all()
    return {"items": [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in items], "total": total}

@router.post("/icp")
def create_icp(body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    rec = IcpRecord(**{k: v for k, v in body.items() if hasattr(IcpRecord, k)})
    db.add(rec); db.commit(); db.refresh(rec)
    return {"id": rec.id, "message": "已创建"}

@router.put("/icp/{rec_id}")
def update_icp(rec_id: int, body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    rec = db.query(IcpRecord).get(rec_id)
    if not rec: raise HTTPException(404, "不存在")
    for k, v in body.items():
        if hasattr(rec, k) and k != "id": setattr(rec, k, v)
    db.commit()
    return {"message": "已更新"}

@router.delete("/icp/{rec_id}")
def delete_icp(rec_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    db.query(IcpRecord).filter(IcpRecord.id == rec_id).delete()
    db.commit()
    return {"message": "已删除"}


# ── 数据同步 ──

@router.post("/sync-from-platform")
def sync_from_platform(db: Session = Depends(get_db), _=Depends(require_admin)):
    """根据 ZDNS 域名数据自动同步信息系统状态。"""
    zdns_domains = {}
    for r in db.execute(text("SELECT domain_name, ip_address, ip_status FROM zdns_domain_map")).fetchall():
        d = (r.domain_name or "").strip().lower()
        if d and d not in zdns_domains:
            zdns_domains[d] = {"ip": r.ip_address or "", "status": r.ip_status or ""}

    def clean_domain(dom):
        dom = (dom or "").strip().lower()
        for prefix in ["https://", "http://"]:
            if dom.startswith(prefix):
                dom = dom[len(prefix):]
        return dom.split("/")[0].split(":")[0]

    updated, offline, deprecated = 0, 0, 0
    items = db.query(InfoSystem).all()
    for sys in items:
        dom = clean_domain(sys.domain)
        if not dom:
            continue
        # 保存清洗后的域名
        if sys.domain != dom:
            sys.domain = dom
        if dom in zdns_domains:
            zdns = zdns_domains[dom]
            zdns_ip = zdns["ip"]
            # 始终带回 IP 地址
            if sys.ip_address != zdns_ip:
                sys.ip_address = zdns_ip
            # 根据 IP 状态设置填报类型
            if zdns["status"] == "离线":
                sys.fill_type = "离线"
                offline += 1
            else:
                sys.fill_type = "自动"
                updated += 1
        else:
            sys.fill_type = "失效"
            deprecated += 1
    db.commit()
    return {"message": f"同步完成：在线 {updated} 条，离线 {offline} 条，失效 {deprecated} 条"}


# ── 等保关联查询 ──

@router.get("/djdj-search")
def search_djdj(q: str = Query(""), db: Session = Depends(get_db), _=Depends(get_current_user)):
    items = db.query(DjDjRecord).filter(DjDjRecord.system_name.contains(q)).limit(20).all()
    return {"items": [{"id": r.id, "system_name": r.system_name, "record_no": r.record_no,
                        "level": r.level, "record_date": str(r.record_date) if r.record_date else None,
                        "org_name": r.org_name} for r in items]}


# ── 供应链 CRUD ──

@router.get("/supply-chain")
def list_supply_chain(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                      search: str = Query(""), db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(SupplyChain)
    if search:
        q = q.filter(SupplyChain.company_name.contains(search))
    total = q.count()
    items = q.order_by(SupplyChain.id).offset((page - 1) * size).limit(size).all()
    return {"items": [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in items], "total": total}

@router.post("/supply-chain")
def create_supply_chain(body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    rec = SupplyChain(**{k: v for k, v in body.items() if hasattr(SupplyChain, k)})
    db.add(rec); db.commit(); db.refresh(rec)
    return {"id": rec.id, "message": "已创建"}

@router.get("/supply-chain/names")
def list_supply_chain_names(db: Session = Depends(get_db), _=Depends(get_current_user)):
    items = db.query(SupplyChain.company_name).order_by(SupplyChain.company_name).all()
    return {"items": [r[0] for r in items]}

# ── 供应链导入导出 ──

# Excel 行业名称到系统选项的映射（Excel 中使用中文顿号分隔，系统使用斜杠）
_INDUSTRY_MAP = {
    "信息运输、软件和信息技术服务业": "信息运输/软件和信息技术服务业",
    "文化、体育和娱乐业": "文化/体育和娱乐业",
    "交通运输、仓储和邮政业": "交通运输/仓储和邮政业",
    "电力、热力、燃气及水生产和供应业": "电力/热力/燃气及水生产和供应业",
    "农、林、牧、渔业": "农/林/牧/渔业",
    "公共管理、社会保障和社会组织": "公共管理/社会保障和社会组织",
    "卫生和社会工作": "卫生和社会工作",
    "居民服务、修理和其他服务业": "居民服务/修理和其他服务业",
    "水利、环境和公共": "水利/环境和公共",
    "科学研究和技术服务业": "科学研究和技术服务业",
    "租聘和商务": "租聘和商务",
    "批发和零售业": "批发和零售业",
    "住宿和餐饮业": "住宿和餐饮业",
    "制造业": "制造业",
    "建筑业": "建筑业",
    "采矿业": "采矿业",
}


def _normalize_industry(val: str) -> str:
    """将 Excel 中的行业名称转换为系统选项格式。"""
    parts = [p.strip() for p in val.split(",") if p.strip()]
    return ",".join(_INDUSTRY_MAP.get(p, p) for p in parts)


@router.post("/supply-chain/import")
def import_supply_chain(file: UploadFile, db: Session = Depends(get_db), _=Depends(require_admin)):
    """从信息系统管理 Excel 文件中导入供应链单位信息（去重）。"""
    wb = openpyxl.load_workbook(io.BytesIO(file.file.read()))
    ws = wb.active
    # 查询已有单位名称用于去重
    existing = {r[0] for r in db.query(SupplyChain.company_name).all()}
    imported, skipped = 0, 0
    seen = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        vals = [_cell_str(v) for v in row]
        if len(vals) <= 51:
            continue
        name = vals[51].strip()
        if not name:
            continue
        if name in seen or name in existing:
            skipped += 1
            continue
        seen.add(name)
        # 行业：合并主行业(col 59) + 其他(col 60)
        industry_raw = vals[59] if len(vals) > 59 else ""
        industry_other = vals[60] if len(vals) > 60 else ""
        if industry_raw and industry_other:
            industry_raw = industry_raw + "," + industry_other
        industry = _normalize_industry(industry_raw) if industry_raw else ""
        # 服务类型：合并 col 61 + col 62
        service_raw = vals[61] if len(vals) > 61 else ""
        service_other = vals[62] if len(vals) > 62 else ""
        if service_raw and service_other and service_other != "无":
            service_raw = service_raw + "," + service_other
        rec = SupplyChain(
            company_name=name,
            credit_code=vals[52] if len(vals) > 52 else "",
            address=vals[53] if len(vals) > 53 else "",
            security_dept=vals[54] if len(vals) > 54 else "",
            security_contact=vals[55] if len(vals) > 55 else "",
            security_phone=vals[56] if len(vals) > 56 else "",
            company_type=vals[57] if len(vals) > 57 else "",
            has_foreign_capital=vals[58] if len(vals) > 58 else "",
            industry=industry,
            service_type=service_raw if service_raw else "",
            importance=vals[63] if len(vals) > 63 else "",
            url_ip_range=vals[64] if len(vals) > 64 else "",
            data_level=vals[65] if len(vals) > 65 else "",
            data_location=vals[66] if len(vals) > 66 else "",
            data_storage=vals[67] if len(vals) > 67 else "",
            db_type=vals[68] if len(vals) > 68 else "",
        )
        db.add(rec)
        imported += 1
    db.commit()
    return {"message": f"导入完成：新增 {imported} 条，跳过重复 {skipped} 条"}


@router.get("/supply-chain/export")
def export_supply_chain(db: Session = Depends(get_db), _=Depends(require_admin)):
    items = db.query(SupplyChain).order_by(SupplyChain.id).all()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "供应链信息"
    ws.append(["单位名称", "信用代码", "注册地址", "安全责任部门", "联系人", "联系电话",
               "单位类型", "境外资本", "服务行业", "服务类型", "重要程度",
               "URL/IP地址段", "数据最高级别", "存储位置", "存储方式", "数据库类型", "备注"])
    for r in items:
        ws.append([r.company_name, r.credit_code, r.address, r.security_dept,
                   r.security_contact, r.security_phone, r.company_type,
                   r.has_foreign_capital, r.industry, r.service_type, r.importance,
                   r.url_ip_range, r.data_level, r.data_location, r.data_storage,
                   r.db_type, r.remark or ""])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=supply_chain_export.xlsx"}
    )

@router.post("/supply-chain/batch-delete")
def batch_delete_supply_chain(body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(400, "请选择记录")
    db.query(SupplyChain).filter(SupplyChain.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"message": f"已删除 {len(ids)} 条"}


@router.put("/supply-chain/{rec_id}")
def update_supply_chain(rec_id: int, body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    rec = db.query(SupplyChain).get(rec_id)
    if not rec: raise HTTPException(404, "不存在")
    for k, v in body.items():
        if hasattr(rec, k) and k != "id": setattr(rec, k, v)
    db.commit()
    return {"message": "已更新"}

@router.delete("/supply-chain/{rec_id}")
def delete_supply_chain(rec_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    db.query(SupplyChain).filter(SupplyChain.id == rec_id).delete()
    db.commit()
    return {"message": "已删除"}


@router.post("/icp/import")
def import_icp(file: UploadFile, db: Session = Depends(get_db), _=Depends(require_admin)):
    wb = openpyxl.load_workbook(io.BytesIO(file.file.read()))
    ws = wb.active
    start = _find_data_start(ws)
    imported = 0
    db.query(IcpRecord).delete()
    for row in ws.iter_rows(min_row=start, values_only=True):
        vals = [_cell_str(v) for v in row]
        if not vals[0] or not vals[0].isdigit(): continue
        rec = IcpRecord(
            icp_no=vals[4] if len(vals) > 4 else "",
            org_name=vals[2] if len(vals) > 2 else "",
            domain=vals[3] if len(vals) > 3 else "",
            record_date=vals[5] if len(vals) > 5 and vals[5] else None,
        )
        db.add(rec); imported += 1
    db.commit()
    return {"message": f"导入完成，共 {imported} 条"}

@router.get("/icp/export")
def export_icp(db: Session = Depends(get_db), _=Depends(require_admin)):
    items = db.query(IcpRecord).all()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "ICP备案"
    ws.append(["ICP备案编号", "备案主体", "备案域名", "备案日期"])
    for r in items:
        ws.append([r.icp_no, r.org_name, r.domain, str(r.record_date) if r.record_date else ""])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=icp_export.xlsx"})
