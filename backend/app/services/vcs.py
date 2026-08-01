"""Version control for code projects — git's model, stored in Postgres.

The three ideas borrowed from git:

  * **Content addressing.** A file's contents are stored once under the SHA-256
    of those contents. Committing an unchanged file costs nothing but a
    reference, so history is cheap even when a project is committed often.
  * **Commits are snapshots, not diffs.** A commit records the whole tree
    (path → blob). Diffs are computed on demand, which makes restoring an old
    state trivial and exact rather than a replay of patches.
  * **A parent chain.** Each commit points at the one before it on its branch,
    so history is a walkable line and branching is just two commits sharing a
    parent.

What is deliberately NOT here: merging. Merge conflict resolution is a genuine
research-grade problem and a half-working merge is worse than none, so branches
diverge and can be compared and restored, but not merged. That is stated in the
UI rather than hidden.
"""
import difflib
import hashlib
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Blob, Commit, CommitFile, Project, ProjectFile, User

log = logging.getLogger("eaios.vcs")

MAX_COMMITS_LISTED = 100
DEFAULT_BRANCH = "main"


def _blob_id(org_id: str, content: str) -> str:
    """Address a blob by its content **within one workspace**.

    The workspace id is part of the hash on purpose. A plain content hash is a
    global key, but blobs are tenant rows: the session filter hides another
    workspace's blob, so the lookup misses and the insert then collides on that
    global key. Two workspaces committing an empty file — or any identical
    boilerplate — would break each other's commits. Salting with the workspace
    keeps deduplication inside a workspace, where it belongs, and makes a
    collision across workspaces impossible.
    """
    return hashlib.sha256(f"{org_id}\x00{content}".encode("utf-8")).hexdigest()


def _blob_for(db: Session, content: str) -> Blob:
    """Fetch or create the blob holding this exact content for this workspace."""
    org_id = db.info.get("org_id") or ""
    digest = _blob_id(org_id, content)
    existing = db.get(Blob, digest)
    if existing is not None:
        return existing
    blob = Blob(id=digest, content=content, size_bytes=len(content.encode("utf-8")))
    db.add(blob)
    db.flush()          # so the same content twice in one commit reuses it
    return blob


def head(db: Session, project_id: str, branch: str = DEFAULT_BRANCH) -> Commit | None:
    """The most recent commit on a branch."""
    return db.scalar(
        select(Commit)
        .where(Commit.project_id == project_id, Commit.branch == branch)
        .order_by(Commit.created_at.desc()))


def tree_of(db: Session, commit: Commit) -> dict[str, str]:
    """path → content for every file in a commit."""
    rows = db.execute(
        select(CommitFile.path, Blob.content)
        .join(Blob, Blob.id == CommitFile.blob_id)
        .where(CommitFile.commit_id == commit.id)).all()
    return {path: content for path, content in rows}


def working_tree(db: Session, project_id: str) -> dict[str, str]:
    """path → content for the project's current, uncommitted files."""
    rows = db.scalars(select(ProjectFile).where(ProjectFile.project_id == project_id))
    return {f.path: (f.content or "") for f in rows}


def status(db: Session, project_id: str, branch: str = DEFAULT_BRANCH) -> dict:
    """What has changed since the last commit — the 'git status' answer."""
    current = working_tree(db, project_id)
    tip = head(db, project_id, branch)
    previous = tree_of(db, tip) if tip else {}

    added = sorted(set(current) - set(previous))
    removed = sorted(set(previous) - set(current))
    modified = sorted(p for p in set(current) & set(previous) if current[p] != previous[p])
    return {
        "branch": branch,
        "head": tip.id if tip else None,
        "added": added, "modified": modified, "removed": removed,
        "clean": not (added or modified or removed),
    }


def commit(db: Session, project: Project, user: User, message: str,
           branch: str = DEFAULT_BRANCH) -> Commit | None:
    """Snapshot the project's current files. Returns None when nothing changed.

    Refusing an empty commit is deliberate: a history where half the entries say
    nothing happened is harder to read than one that only records real change.
    """
    state = status(db, project.id, branch)
    if state["clean"]:
        return None

    tip = head(db, project.id, branch)
    current = working_tree(db, project.id)

    c = Commit(project_id=project.id, branch=branch, message=message.strip()[:500],
               author_id=user.id, author_name=user.full_name,
               parent_id=tip.id if tip else None, file_count=len(current))
    db.add(c)
    db.flush()

    languages = {f.path: f.language for f in
                 db.scalars(select(ProjectFile).where(ProjectFile.project_id == project.id))}
    for path, content in current.items():
        blob = _blob_for(db, content)
        db.add(CommitFile(commit_id=c.id, path=path, blob_id=blob.id,
                          language=languages.get(path, "plaintext")))
    db.commit()
    db.refresh(c)
    log.info("commit %s on %s/%s by %s (%d files)",
             c.id[:8], project.name, branch, user.full_name, len(current))
    return c


def history(db: Session, project_id: str, branch: str | None = None,
            limit: int = MAX_COMMITS_LISTED) -> list[Commit]:
    q = select(Commit).where(Commit.project_id == project_id)
    if branch:
        q = q.where(Commit.branch == branch)
    return list(db.scalars(q.order_by(Commit.created_at.desc()).limit(limit)))


def branches(db: Session, project_id: str) -> list[dict]:
    rows = db.execute(
        select(Commit.branch, func.count(Commit.id), func.max(Commit.created_at))
        .where(Commit.project_id == project_id)
        .group_by(Commit.branch)).all()
    out = [{"name": b, "commits": n, "updated_at": ts.isoformat() if ts else None}
           for b, n, ts in rows]
    if not any(b["name"] == DEFAULT_BRANCH for b in out):
        out.insert(0, {"name": DEFAULT_BRANCH, "commits": 0, "updated_at": None})
    return sorted(out, key=lambda b: (b["name"] != DEFAULT_BRANCH, b["name"]))


def create_branch(db: Session, project: Project, user: User, name: str,
                  from_branch: str = DEFAULT_BRANCH) -> Commit | None:
    """Start a branch at the tip of another one.

    Implemented as a commit on the new branch carrying the same tree: the branch
    then has a starting point of its own, and the two lines diverge from there.
    """
    source = head(db, project.id, from_branch)
    if source is None:
        return None
    tree = tree_of(db, source)
    c = Commit(project_id=project.id, branch=name.strip()[:80],
               message=f"Branched from {from_branch}", author_id=user.id,
               author_name=user.full_name, parent_id=source.id, file_count=len(tree))
    db.add(c)
    db.flush()
    langs = {e.path: e.language for e in
             db.scalars(select(CommitFile).where(CommitFile.commit_id == source.id))}
    for path, content in tree.items():
        blob = _blob_for(db, content)
        db.add(CommitFile(commit_id=c.id, path=path, blob_id=blob.id,
                          language=langs.get(path, "plaintext")))
    db.commit()
    db.refresh(c)
    return c


def diff(db: Session, project_id: str, to_commit: Commit,
         from_commit: Commit | None = None) -> list[dict]:
    """Unified diff between two commits — or, when ``from_commit`` is omitted,
    between a commit and its parent (what that commit changed)."""
    if from_commit is None and to_commit.parent_id:
        from_commit = db.get(Commit, to_commit.parent_id)

    after = tree_of(db, to_commit)
    before = tree_of(db, from_commit) if from_commit else {}

    out: list[dict] = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old == new:
            continue
        kind = "added" if old is None else "removed" if new is None else "modified"
        patch = "\n".join(difflib.unified_diff(
            (old or "").splitlines(), (new or "").splitlines(),
            fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""))
        added = sum(1 for line in patch.splitlines()
                    if line.startswith("+") and not line.startswith("+++"))
        deleted = sum(1 for line in patch.splitlines()
                      if line.startswith("-") and not line.startswith("---"))
        out.append({"path": path, "change": kind, "patch": patch,
                    "additions": added, "deletions": deleted})
    return out


def diff_working(db: Session, project_id: str, branch: str = DEFAULT_BRANCH) -> list[dict]:
    """What is uncommitted right now, against the branch tip."""
    tip = head(db, project_id, branch)
    before = tree_of(db, tip) if tip else {}
    after = working_tree(db, project_id)

    out: list[dict] = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old == new:
            continue
        kind = "added" if old is None else "removed" if new is None else "modified"
        patch = "\n".join(difflib.unified_diff(
            (old or "").splitlines(), (new or "").splitlines(),
            fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""))
        out.append({"path": path, "change": kind, "patch": patch})
    return out


def checkout(db: Session, project: Project, target: Commit, user: User) -> dict:
    """Restore the working files to a commit's state.

    Nothing is lost: anything uncommitted is committed first, on a rescue
    branch, so 'restore an old version' can never silently discard work the
    person forgot to commit.
    """
    rescued = None
    if not status(db, project.id, target.branch)["clean"]:
        rescued = commit(db, project, user,
                         f"Auto-saved before restoring {target.id[:8]}",
                         branch=f"rescue-{target.id[:8]}")

    tree = tree_of(db, target)
    existing = {f.path: f for f in
                db.scalars(select(ProjectFile).where(ProjectFile.project_id == project.id))}

    langs = {e.path: e.language for e in
             db.scalars(select(CommitFile).where(CommitFile.commit_id == target.id))}

    for path, content in tree.items():
        f = existing.get(path)
        if f is None:
            db.add(ProjectFile(project_id=project.id, path=path,
                               language=langs.get(path, "plaintext"), content=content,
                               size_bytes=len(content.encode("utf-8")), updated_by=user.id))
        elif f.content != content:
            f.content = content
            f.size_bytes = len(content.encode("utf-8"))
            f.updated_by = user.id
            f.ydoc = None        # CRDT state no longer matches; rebuilt from text
    # Files that did not exist at that commit go away.
    for path, f in existing.items():
        if path not in tree:
            db.delete(f)
    db.commit()
    return {"restored": target.id, "files": len(tree),
            "rescued_to": rescued.branch if rescued else None}
