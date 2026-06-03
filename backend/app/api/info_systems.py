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
from app.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/info-systems", tags=["信息系统"])


def _gen_asset_id():
    return f"IS-{datetime.now().strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:4]}"


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


@router.post("")
def create_system(body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not body.get("asset_id"):
        body["asset_id"] = _gen_asset_id()
    if db.query(InfoSystem).filter(InfoSystem.asset_id == body["asset_id"]).first():
        raise HTTPException(400, "资产ID已存在")
    sys = InfoSystem(**{k: v for k, v in body.items() if hasattr(InfoSystem, k)})
    db.add(sys); db.commit(); db.refresh(sys)
    return {"id": sys.id, "message": "已创建"}


@router.put("/{sys_id}")
def update_system(sys_id: int, body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    sys = db.query(InfoSystem).get(sys_id)
    if not sys: raise HTTPException(404, "不存在")
    for k, v in body.items():
        if hasattr(sys, k) and k != "id":
            setattr(sys, k, v)
    db.commit()
    return {"message": "已更新"}


@router.delete("/{sys_id}")
def delete_system(sys_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    db.query(InfoSystem).filter(InfoSystem.id == sys_id).delete()
    db.commit()
    return {"message": "已删除"}


# ── Excel 导入 ──

@router.post("/import")
def import_excel(file: UploadFile, db: Session = Depends(get_db), _=Depends(require_admin)):
    wb = openpyxl.load_workbook(io.BytesIO(file.file.read()))
    ws = wb.active
    db.query(InfoSystem).delete()
    start = _find_data_start(ws)
    imported = 0
    for row in ws.iter_rows(min_row=start, values_only=True):
        vals = [str(v) if v else "" for v in row]
        if not any(vals): continue
        sys = InfoSystem(
            asset_id=_gen_asset_id(),
            system_name=vals[3] if len(vals) > 3 else "",
            system_type=vals[4] if len(vals) > 4 else "",
            sub_type=vals[5] if len(vals) > 5 else "",
            ip_address=vals[6] if len(vals) > 6 else "",
            domain=vals[7] if len(vals) > 7 else "",
            djdj_status=vals[8] if len(vals) > 8 else "",
            djdj_sys_name=vals[12] if len(vals) > 12 else "",
            djdj_date=vals[13] if len(vals) > 13 and vals[13] else None,
            djdj_no=vals[14] if len(vals) > 14 else "",
            org_name=vals[2] if len(vals) > 2 else "",
            dept_name=vals[25] if len(vals) > 25 else "",
            contact=vals[27] if len(vals) > 27 else "",
            contact_phone=vals[28] if len(vals) > 28 else "",
            fill_type="导入",
            remark=vals[11] if len(vals) > 11 else "",
        )
        db.add(sys); imported += 1
    db.commit()
    return {"message": f"导入完成，共 {imported} 条"}


# ── Excel 导出 ──

@router.get("/export")
def export_excel(db: Session = Depends(get_db), _=Depends(require_admin)):
    items = db.query(InfoSystem).all()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "信息系统"
    headers = ["资产ID", "系统名称", "类型", "IP", "域名", "单位", "运维单位", "联系人", "电话", "等保编号", "等保等级", "填报类型"]
    ws.append(headers)
    for r in items:
        ws.append([r.asset_id, r.system_name, r.system_type, r.ip_address, r.domain,
                    r.org_name, r.dept_name, r.contact, r.contact_phone, r.djdj_no, r.djdj_level, r.fill_type])
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
        d["dept_name"] = r.eval_org or ""
        result.append(d)
    return {"items": result, "total": total}

@router.post("/djdj")
def create_djdj(body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    data = dict(body)
    if "dept_name" in data:
        data["eval_org"] = data.pop("dept_name")
    rec = DjDjRecord(**{k: v for k, v in data.items() if hasattr(DjDjRecord, k)})
    db.add(rec); db.commit(); db.refresh(rec)
    return {"id": rec.id, "message": "已创建"}

@router.put("/djdj/{rec_id}")
def update_djdj(rec_id: int, body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    rec = db.query(DjDjRecord).get(rec_id)
    if not rec: raise HTTPException(404, "不存在")
    data = dict(body)
    if "dept_name" in data:
        data["eval_org"] = data.pop("dept_name")
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
    for r in db.execute(text("SELECT domain_name, ip_address FROM zdns_domain_map")).fetchall():
        d = (r.domain_name or "").strip().lower()
        if d and d not in zdns_domains:
            zdns_domains[d] = r.ip_address

    def clean_domain(dom):
        dom = (dom or "").strip().lower()
        for prefix in ["https://", "http://"]:
            if dom.startswith(prefix):
                dom = dom[len(prefix):]
        return dom.split("/")[0].split(":")[0]

    updated, deprecated = 0, 0
    items = db.query(InfoSystem).all()
    for sys in items:
        dom = clean_domain(sys.domain)
        if not dom:
            continue
        # 保存清洗后的域名
        if sys.domain != dom:
            sys.domain = dom
        if dom in zdns_domains:
            zdns_ip = zdns_domains[dom] or ""
            if sys.ip_address != zdns_ip and zdns_ip:
                sys.ip_address = zdns_ip
            sys.fill_type = "自动"
            updated += 1
        else:
            sys.fill_type = "失效"
            deprecated += 1
    db.commit()
    return {"message": f"同步完成：更新 {updated} 条，标记失效 {deprecated} 条"}


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
