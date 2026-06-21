"""Backfill: recompute execution_reasoning embeddings with the cleaned embed text
(embeddings.embed_text_for) instead of the legacy json.dumps(reasoning).

Scoped to currently-embedded rows of a project (default 13 = L33T, the real pool)
so it replaces dirty vectors in place and touches nothing synthetic/unembedded.

Run: .venv/bin/python -m scripts.reembed [project_id]
"""

import asyncio
import sys

from sqlalchemy import text

from app import embeddings
from app.db import SessionLocal


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in vec) + "]"


async def main(project_id: int) -> None:
    if not embeddings.is_available():
        raise SystemExit("embeddings extra not available; cannot backfill")
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    """
                    select er.id, er.reasoning, e.notes
                    from execution_reasoning er
                    join executions e on e.id = er.execution_id
                    join test_case_versions tcv on tcv.id = e.version_id
                    join test_cases c on c.id = tcv.case_id
                    where c.project_id = :pid and er.embedding is not null
                    """
                ),
                {"pid": project_id},
            )
        ).all()
        n_set = n_null = 0
        for rid, reasoning, notes in rows:
            embed_text = embeddings.embed_text_for(reasoning, notes)
            if embed_text:
                vec = embeddings.embed(embed_text)
                await s.execute(
                    text(
                        "update execution_reasoning set embedding = :v, search_text = :t"
                        " where id = :i"
                    ),
                    {"v": _vec_literal(vec), "t": embed_text, "i": rid},
                )
                n_set += 1
            else:
                await s.execute(
                    text(
                        "update execution_reasoning set embedding = NULL, search_text = NULL"
                        " where id = :i"
                    ),
                    {"i": rid},
                )
                n_null += 1
        await s.commit()
        print(f"project={project_id}  re-embedded={n_set}  nulled={n_null}  total={len(rows)}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 13))
