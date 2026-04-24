BEGIN;

-- Revoca ejecución a roles no-admin (por si los otorgaste antes)
REVOKE EXECUTE ON FUNCTION fin.fn_periodo_cerrar(int,int,citext,text) FROM fin_ro, fin_rw;
REVOKE EXECUTE ON FUNCTION fin.fn_periodo_abrir(int,int,citext,text)  FROM fin_ro, fin_rw;

-- Otorga solo a admin
GRANT EXECUTE ON FUNCTION fin.fn_periodo_cerrar(int,int,citext,text) TO fin_admin;
GRANT EXECUTE ON FUNCTION fin.fn_periodo_abrir(int,int,citext,text)  TO fin_admin;

COMMIT;