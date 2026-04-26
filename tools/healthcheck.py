from __future__ import annotations

from db.session import get_session_local
from services.fondos_rendir import diagnosticar_setup_contable


def main() -> int:
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        setup = diagnosticar_setup_contable(db)
        print("OK: setup contable fondos por rendir")
        print(f"  Anticipo: {setup['anticipo']['codigo']} - {setup['anticipo']['nombre']}")
        print(f"  Caja: {setup['caja']['codigo']} - {setup['caja']['nombre']}")
        print(f"  Gasto: {setup['gasto']['codigo']} - {setup['gasto']['nombre']}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
