"""自动关联 — 解析 vm_folder 匹配部门 + 备注匹配负责人。"""
import logging
import threading
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db, SessionLocal
from app.api.deps import require_admin
from app.schemas.asset import AutoMatchPreview, AutoMatchResult, MatchPreviewItem

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assets/auto-match", tags=["自动关联"])

# 后台任务状态
_task_status: dict = {}


def _run_match_owner():
    """后台线程执行匹配负责人。"""
    db = SessionLocal()
    try:
        from app.utils.security import hash_password
        from app.services.external_api_service import fetch_staff
        _task_status["owner"] = {"running": True, "message": "正在查询外部API..."}

        # 清理
        db.execute(text("DELETE FROM users WHERE username LIKE 'user_%'"))
        db.commit()

        vms = db.execute(text(
            "SELECT v.id, v.vm_name, v.remark, a.department_id, d.dwmc, d.dwbm FROM vm_inventory v "
            "LEFT JOIN asset_inventory a ON v.vm_name = a.vm_name "
            "LEFT JOIN departments d ON a.department_id = d.id "
            "WHERE a.department_id IS NOT NULL AND a.owner_user_id IS NULL "
            "AND v.remark IS NOT NULL AND v.remark != ''"
        )).fetchall()

        # 收集人名
        all_names = set()
        for v in vms:
            for name in _extract_names(v.remark):
                all_names.add(name)
        name_list = sorted(all_names)

        # 查询API
        name_cache = {}
        api_errors = []
        for idx, name in enumerate(name_list):
            try:
                staff_list = fetch_staff(db, xm=name)
                staff_list.sort(key=lambda x: (1 if x.get("GH", "0").startswith("10") else 0, int(x.get("GH", "0") or "0")), reverse=True)
                name_cache[name] = staff_list
            except Exception as e:
                api_errors.append(f"{name}:{e}")
                name_cache[name] = []
            if idx % 10 == 0:
                _task_status["owner"] = {"running": True, "message": f"查询API中 {idx+1}/{len(name_list)}..."}

        # 匹配VM
        matched = 0
        for v in vms:
            names = _extract_names(v.remark)
            if not names:
                continue
            for name in names:
                user = db.execute(text("SELECT id FROM users WHERE name = :name"), {"name": name}).fetchone()
                if user:
                    db.execute(text(
                        "UPDATE asset_inventory SET owner_user_id=:u, claimed_by=:u, claim_status='manual', claimed_at=NOW() WHERE vm_name=:n"
                    ), {"u": user.id, "n": v.vm_name})
                    db.commit()
                    matched += 1
                    break
                staff_list = name_cache.get(name, [])
                # 检查VM的部门链(向上追溯父部门)
                vm_codes = {v.dwbm}
                current_dwbm = v.dwbm
                for _ in range(3):
                    parent_row = db.execute(text("SELECT lsdwh FROM departments WHERE dwbm=:d"), {"d": current_dwbm}).fetchone()
                    if parent_row and parent_row.lsdwh:
                        vm_codes.add(parent_row.lsdwh)
                        current_dwbm = parent_row.lsdwh
                    else:
                        break
                found = None
                for s in staff_list:
                    sd = (s.get("SZDWBM") or "").strip()
                    gh = s.get("GH", "").strip()
                    if sd and any(sd == c or c.startswith(sd) or sd.startswith(c) for c in vm_codes):
                        if gh.startswith("10"):
                            found = s
                            break
                        if not found:
                            found = s
                if found:
                    gh = found.get("GH", "").strip()
                    xm = found.get("XM", "").strip()
                    email = (found.get("DZYX") or "").strip()
                    phone = (found.get("BGDH") or "").strip()
                    mobile = (found.get("YDDH") or "").strip()
                    gender = "男" if found.get("XBM") == "1" else "女" if found.get("XBM") == "2" else ""
                    exist = db.execute(text("SELECT id FROM users WHERE gh=:g"), {"g": gh}).fetchone()
                    if exist:
                        db.execute(text(
                            "UPDATE users SET name=:n,email=COALESCE(NULLIF(:e,''),email),"
                            "phone=COALESCE(NULLIF(:p,''),phone),mobile=COALESCE(NULLIF(:m,''),mobile),"
                            "gender=COALESCE(NULLIF(:g2,''),gender) WHERE id=:i"
                        ), {"n": xm, "e": email, "p": phone, "m": mobile, "g2": gender, "i": exist.id})
                        db.commit()
                        uid = exist.id
                    else:
                        db.execute(text(
                            "INSERT INTO users (username,password_hash,role,name,gh,gender,email,phone,mobile,department_id,user_type,is_active) "
                            "VALUES (:u,:p,'user',:n,:g,:g2,:e,:ph,:m,:d,'internal',1)"
                        ), {"u": gh, "p": hash_password(gh), "n": xm, "g": gh, "g2": gender, "e": email if email else None, "ph": phone if phone else None, "m": mobile if mobile else None, "d": v.department_id})
                        db.commit()
                        uid = db.execute(text("SELECT id FROM users WHERE gh=:g"), {"g": gh}).fetchone().id
                    db.execute(text(
                        "INSERT INTO asset_inventory (vm_name, owner_user_id, claimed_by, claim_status, claimed_at) "
                        "VALUES (:n, :u, :u, 'manual', NOW()) ON DUPLICATE KEY UPDATE owner_user_id=:u, claimed_by=:u, claim_status='manual', claimed_at=NOW()"
                    ), {"n": v.vm_name, "u": uid})
                    db.commit()
                    matched += 1
                    break
        msg = f"完成：共{len(vms)}个VM，匹配{matched}人，API查询{len(name_list)}人"
        if api_errors:
            msg += f"，API错误{len(api_errors)}个"
        _task_status["owner"] = {"running": False, "message": msg}
        logger.info(f"后台匹配负责人: {msg}")
    except Exception as e:
        _task_status["owner"] = {"running": False, "message": f"任务失败：{e}"}
        logger.error(f"后台匹配负责人失败: {e}")
    finally:
        db.close()


def _seq_match(abbr: str, full: str) -> bool:
    """检查 abbr 的每个字符是否按序出现在 full 中。"""
    idx = 0
    for ch in abbr:
        idx = full.find(ch, idx)
        if idx == -1:
            return False
        idx += 1
    return True


def _extract_candidates(folder: str) -> list[tuple[str, str]]:
    candidates = []
    for seg in folder.split("/"):
        seg = seg.strip()
        if not seg:
            continue
        for prefix in ["东北林业大学-", "东北林业大学－"]:
            if seg.startswith(prefix):
                seg = seg[len(prefix):]
                break
        for sub in seg.split("-"):
            sub = sub.strip()
            if not sub or len(sub) < 2:
                continue
            skip = {"other_dept", "department", "dashboard", "datagovernance", "datamiddleplatform", "vm", "server", "admin", "test", "dev"}
            if sub.lower() in skip:
                continue
            if sub.isdigit() and 3 <= len(sub) <= 6:
                candidates.append((sub, "code"))
            elif any('一' <= c <= '鿿' for c in sub):
                candidates.append((sub, "name"))
            elif len(sub) >= 3:
                candidates.append((sub, "code"))
    return candidates


def _match_folder_to_dept(db: Session, folder: str) -> tuple:
    if not folder:
        return None, None, None
    candidates = _extract_candidates(folder)
    if not candidates:
        return None, None, None
    depts = db.execute(text("SELECT id, dwmc, dwjc, dwbm FROM departments")).fetchall()
    code_map = {}
    for d in depts:
        if d.dwbm:
            for sl in [2, 3, 4, 5, 6]:
                if len(d.dwbm) >= sl:
                    code_map.setdefault(d.dwbm[-sl:], []).append(d)
    name_candidates = [v for v, t in candidates if t == "name" and len(v) >= 2]
    all_code_matches = []
    for val, typ in reversed(candidates):
        if typ == "code" and val in code_map:
            for d in code_map[val]:
                verified = False
                dn = (d.dwmc or "").lower()
                for nc in name_candidates:
                    nl = nc.lower()
                    if _seq_match(nl, dn) or _seq_match(dn, nl) or nl in dn or dn in nl:
                        verified = True
                        break
                all_code_matches.append((d, val, verified))
    if all_code_matches:
        for d, seg, verified in all_code_matches:
            if verified:
                return d.id, d.dwmc, seg
        unique_ids = set(m.id for m, _, _ in all_code_matches)
        if len(unique_ids) == 1:
            d = all_code_matches[0][0]
            return d.id, d.dwmc, all_code_matches[0][1]
        d = all_code_matches[0][0]
        return d.id, d.dwmc, all_code_matches[0][1]
    for val, typ in reversed(candidates):
        if typ == "name" and len(val) >= 2:
            for d in depts:
                if d.dwjc and d.dwjc.lower() == val.lower():
                    return d.id, d.dwmc, val
            for d in depts:
                if _seq_match(val.lower(), (d.dwmc or "").lower()):
                    return d.id, d.dwmc, val
            for d in depts:
                if d.dwbm and d.dwbm.lower() == val.lower():
                    return d.id, d.dwmc, val
    return None, None, None


def _extract_names(text: str) -> list[str]:
    if not text:
        return []
    names = []
    buf = ""
    for ch in text:
        if '一' <= ch <= '鿿':
            buf += ch
        else:
            if 2 <= len(buf) <= 4:
                names.append(buf)
            buf = ""
    if 2 <= len(buf) <= 4:
        names.append(buf)
    return names


@router.get("/preview", response_model=AutoMatchPreview)
def preview_match(db: Session = Depends(get_db), _=Depends(require_admin)):
    vms = db.execute(text(
        "SELECT v.id, v.vm_name, v.vm_folder, v.resource_pool FROM vm_inventory v "
        "LEFT JOIN asset_inventory a ON v.vm_name = a.vm_name "
        "WHERE (a.id IS NULL OR a.claim_status = 'unlinked') "
        "AND ((v.vm_folder IS NOT NULL AND v.vm_folder != '') OR (v.resource_pool IS NOT NULL AND v.resource_pool != ''))"
    )).fetchall()
    items = []
    for v in vms:
        source = (v.vm_folder or "") if (v.vm_folder or "") else (v.resource_pool or "")
        dept_id, dept_name, seg = _match_folder_to_dept(db, source)
        if dept_id:
            items.append(MatchPreviewItem(vm_id=v.id, vm_name=v.vm_name, vm_folder=source, matched_segment=seg, matched_dept_id=dept_id, matched_dept_name=dept_name))
    return AutoMatchPreview(items=items, total_vms=len(vms), matched_count=len(items))


@router.post("", response_model=AutoMatchResult)
def execute_match(db: Session = Depends(get_db), _=Depends(require_admin)):
    vms = db.execute(text(
        "SELECT v.id, v.vm_name, v.vm_folder, v.resource_pool FROM vm_inventory v "
        "LEFT JOIN asset_inventory a ON v.vm_name = a.vm_name "
        "WHERE (a.id IS NULL OR a.claim_status = 'unlinked') "
        "AND ((v.vm_folder IS NOT NULL AND v.vm_folder != '') OR (v.resource_pool IS NOT NULL AND v.resource_pool != ''))"
    )).fetchall()
    details = []
    matched = 0
    failed = 0
    for v in vms:
        source = (v.vm_folder or "") if (v.vm_folder or "") else (v.resource_pool or "")
        dept_id, dept_name, seg = _match_folder_to_dept(db, source)
        if dept_id:
            try:
                db.execute(text(
                    "INSERT INTO asset_inventory (vm_name, department_id, claim_status, claimed_at) "
                    "VALUES (:n, :d, 'auto', NOW()) "
                    "ON DUPLICATE KEY UPDATE department_id=:d, claim_status='auto', claimed_at=NOW()"
                ), {"n": v.vm_name, "d": dept_id})
                db.commit()
                matched += 1
                details.append({"vm_name": v.vm_name, "folder": source, "dept": dept_name, "status": "success"})
            except Exception as e:
                failed += 1
                details.append({"vm_name": v.vm_name, "folder": source, "dept": dept_name, "status": f"error:{e}"})
                db.rollback()
    logger.info(f"自动分组完成：共{len(vms)}VM，匹配{matched}，失败{failed}")
    return AutoMatchResult(total_vms=len(vms), matched=matched, failed=failed, details=details)


@router.post("/start-owner")
def start_match_owner(_=Depends(require_admin)):
    """启动后台匹配负责人任务。"""
    if _task_status.get("owner", {}).get("running"):
        return {"running": True, "message": "任务已在运行中..."}
    _task_status["owner"] = {"running": True, "message": "正在启动..."}
    t = threading.Thread(target=_run_match_owner, daemon=True)
    t.start()
    return {"running": True, "message": "任务已开始，正在查询外部API..."}


@router.get("/status-owner")
def status_match_owner(_=Depends(require_admin)):
    """查询后台匹配负责人任务状态。"""
    st = _task_status.get("owner", {})
    return {"running": st.get("running", False), "message": st.get("message", "未开始")}
