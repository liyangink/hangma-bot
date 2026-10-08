"""离线确认的持久登记原型：原子保留来源与显著性预算，不执行或批准发布。

同一活动必须使用同一个数据库路径；本模块不能证明数据库外的历史完整，
也不能阻止人为删除/另建数据库。正式执行器仍须绑定路径及文件身份。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from contextlib import contextmanager
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from typing import Mapping

import confirmation_draft as analysis
import confirmation_pairing as pairing


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class ConfirmationRegistry:
    """单活动的来源消费和误报预算账本；并发写通过SQLite事务串行化。"""

    def __init__(self, path: Path, *, campaign_id: str, allocations: list[float]):
        """创建或核对同一活动，分配总额不超过0.05；已有设置不匹配即拒绝。"""
        if not isinstance(campaign_id,str) or not campaign_id.strip():
            raise ValueError('活动身份缺失')
        if not allocations or any(type(x) not in (int,float) or not 0<x<=.05 for x in allocations):
            raise ValueError('无效显著性分配')
        if sum(Decimal(str(x)) for x in allocations)>Decimal('.05'):
            raise ValueError('活动总显著性预算超过0.05')
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS roots (id TEXT PRIMARY KEY, content TEXT UNIQUE NOT NULL, draw TEXT UNIQUE NOT NULL, mix TEXT NOT NULL, exposures TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, slot INTEGER UNIQUE NOT NULL, digest TEXT NOT NULL, receipt TEXT NOT NULL)')
            config=_json({'schema':'confirmation-registry-draft/1','campaign_id':campaign_id,'allocations':allocations})
            old=db.execute("SELECT value FROM metadata WHERE key='config'").fetchone()
            if old is None:db.execute("INSERT INTO metadata VALUES ('config',?)",(config,))
            elif old[0]!=config:raise ValueError('已有活动配置不匹配，禁止重置预算')

    @contextmanager
    def _transaction(self):
        """所有写入先取得事务锁；失败整笔回滚，重试不会部分占根或占额度。"""
        db=sqlite3.connect(str(self.path),timeout=5,isolation_level=None)
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _ledger(db):
        return [{'source_root_id':row[0],'root_content_digest':row[1],'independence_id':row[2],
            'opponent_mix':row[3],'usage':'confirmation','exposures':json.loads(row[4])}
            for row in db.execute('SELECT id,content,draw,mix,exposures FROM roots ORDER BY id')]

    def source_ledger(self):
        """取得可冻结的来源快照；用途为confirmation不代表已证明未曝光。"""
        with self._transaction() as db:return self._ledger(db)

    def register_root(self, plan: Mapping):
        """登记赛程原型身份；已知同ID相同内容可幂等返回，任何身份别名冲突拒绝。"""
        body=dict(plan);content=body.pop('root_content_digest',None)
        if body.get('schema')!=pairing.SCHEMA or analysis.digest(body)!=content:
            raise ValueError('来源计划摘要/结构不符')
        root_id=body.get('source_root_id');draw=body.get('independence_id');mix=body.get('opponent_mix')
        if not isinstance(root_id,str) or not root_id or not isinstance(draw,str) or not draw or mix not in ('H','M'):
            raise ValueError('来源身份不完整')
        with self._transaction() as db:
            old=db.execute('SELECT content,draw,mix FROM roots WHERE id=?',(root_id,)).fetchone()
            if old is not None:
                if old!=(content,draw,mix):raise ValueError('同根ID内容漂移')
                return
            try:db.execute('INSERT INTO roots VALUES (?,?,?,?,?)',(root_id,content,draw,mix,'[]'))
            except sqlite3.IntegrityError as error:raise ValueError('来源内容或随机身份已登记，禁止别名重复') from error

    def record_exposure(self, root_id: str, *, event_id: str, evidence: str):
        """记录开发/诊断消费；只追加，不允许把曝光根重新清空为未见。"""
        if not event_id or not evidence:raise ValueError('曝光事件和证据缺失')
        event={'event_id':event_id,'kind':'external_exposure','evidence':evidence}
        with self._transaction() as db:
            row=db.execute('SELECT exposures FROM roots WHERE id=?',(root_id,)).fetchone()
            if row is None:raise ValueError('根未登记')
            values=json.loads(row[0])
            for old in values:
                if old['event_id']==event_id:
                    if old!=event:raise ValueError('曝光事件身份冲突')
                    return
            values.append(event)
            db.execute('UPDATE roots SET exposures=? WHERE id=?',(_json(values),root_id))

    def reserve_attempt(self, attempt_id: str, registration: Mapping):
        """在运行前原子占用全部根与一个显著性槽；失败不返还，可同身份恢复。

        registration沿用分析原型的完整预登记形状，额外绑定候选源码摘要。
        来源快照若已变化则拒绝，不能拿旧的未见快照覆盖已曝光事实。
        返回receipt保留消费前快照，供后续分析；不代表执行完成或统计通过。
        """
        if not isinstance(attempt_id,str) or not attempt_id:raise ValueError('执行身份缺失')
        source=registration.get('candidate_source_sha256')
        if not isinstance(source,str) or len(source)!=64 or any(c not in '0123456789abcdef' for c in source):
            raise ValueError('候选源码摘要缺失')
        frozen=analysis.digest(registration)
        with self._transaction() as db:
            existing=db.execute('SELECT digest,receipt FROM attempts WHERE id=?',(attempt_id,)).fetchone()
            if existing is not None:
                if existing[0]!=frozen:raise ValueError('恢复的执行身份/预登记不一致')
                return json.loads(existing[1])
            config=json.loads(db.execute("SELECT value FROM metadata WHERE key='config'").fetchone()[0])
            multiplicity=registration.get('multiplicity',{})
            if multiplicity.get('campaign_id')!=config['campaign_id'] or multiplicity.get('allocations')!=config['allocations']:
                raise ValueError('预登记试图另建活动或增加误报预算')
            ledger=self._ledger(db)
            analysis.validate_registration(registration,frozen_digest=frozen,source_ledger=ledger)
            slot=multiplicity['slot']
            if db.execute('SELECT id FROM attempts WHERE slot=?',(slot,)).fetchone():
                raise ValueError('显著性槽已消费，不得重用')
            receipt={'schema':'confirmation-reservation-draft/1','attempt_id':attempt_id,
                'registration_digest':frozen,'registration':dict(registration),'source_ledger_before':ledger,
                'alpha_consumed':registration['alpha'],'slot':slot,'status':'RESERVED_BEFORE_EXECUTION',
                'release_eligible':False}
            db.execute('INSERT INTO attempts VALUES (?,?,?,?)',(attempt_id,slot,frozen,_json(receipt)))
            for root in registration['roots']:
                event={'event_id':'confirmation:'+attempt_id,'kind':'reserved_before_execution',
                    'registration_digest':frozen}
                db.execute('UPDATE roots SET exposures=? WHERE id=?',(_json([event]),root['source_root_id']))
            return receipt

    def attempts(self):
        """读取已永久消耗的槽位与预登记；实际执行结果由独立结果核验器提供。"""
        with self._transaction() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT receipt FROM attempts ORDER BY slot')]
