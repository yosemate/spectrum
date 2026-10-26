"""
Módulo de Banco de Dados e Gestão de Usuários (SQLite)
SPECTRUM-LAB PRO v3.1

Garante que o arquivo usuarios.db seja salvo sempre na mesma pasta física
do executável compilado (.exe) ou do script Python.
"""

import sys
import os
import sqlite3
import datetime
from contextlib import contextmanager
from typing import List, Dict, Optional, Tuple
from runtime_data import resolve_database_path
from password_hashing import hash_password, verify_password, validate_new_password


def get_database_path(db_name: str = "usuarios.db") -> str:
    """
    Retorna o caminho absoluto do banco de dados SQLite.
    Se a aplicação estiver congelada/compilada pelo PyInstaller (.exe),
    utiliza o diretório de sys.executable. Caso contrário, utiliza o diretório
    do script local.
    """
    return resolve_database_path(db_name)


class DatabaseManager:
    """
    Gerenciador do banco de dados SQLite para controle de acesso do SpectrumLab Pro.
    Tabela 'usuarios' com id, username, password_hash (PBKDF2-SHA256 com sal) e role ('admin' ou 'operador').
    Não cria usuário padrão: o primeiro administrador é cadastrado na primeira execução.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path if db_path else get_database_path("usuarios.db")
        self.init_db()

    @contextmanager
    def _get_connection(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn=sqlite3.connect(self.db_path,timeout=5.0)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def hash_password(password: str) -> str:
        """Gera hash PBKDF2-HMAC-SHA256 com sal aleatório."""
        return hash_password(password)

    def init_db(self):
        """Cria as tabelas. Não cria usuário padrão."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'operador'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS leituras_historico (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo_amostra TEXT,
                    timestamp TEXT,
                    operador TEXT,
                    metodo_analitico TEXT,
                    intensidade_global_adc INTEGER,
                    pico_espectral_nm INTEGER,
                    pico_espectral_adc INTEGER,
                    razao_celulose REAL,
                    razao_agua REAL,
                    kappa_estimado REAL,
                    kappa_classificacao TEXT,
                    adc_610 REAL,
                    adc_680 REAL,
                    adc_730 REAL,
                    adc_760 REAL,
                    adc_810 REAL,
                    adc_860 REAL,
                    ref_610 REAL,
                    ref_680 REAL,
                    ref_730 REAL,
                    ref_760 REAL,
                    ref_810 REAL,
                    ref_860 REAL
                )
            """)
            cursor.execute("""CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, reading_id INTEGER NOT NULL,
                actor TEXT NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL,
                timestamp TEXT NOT NULL)""")
            # Verificação e migração automática de colunas para bancos pré-existentes
            cursor.execute("PRAGMA table_info(leituras_historico)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            expected_cols = {
                "invalidated_at":"TEXT", "invalidated_by":"TEXT", "invalidation_reason":"TEXT",
                "origin":"TEXT", "trial_context_json":"TEXT",
                "calibration_id":"TEXT", "calibration_snapshot":"TEXT",
                "acquisition_count":"INTEGER", "raw_scans_json":"TEXT",
                "codigo_amostra": "TEXT", "timestamp": "TEXT", "operador": "TEXT", "metodo_analitico": "TEXT",
                "intensidade_global_adc": "INTEGER", "pico_espectral_nm": "INTEGER", "pico_espectral_adc": "INTEGER",
                "razao_celulose": "REAL", "razao_agua": "REAL", "kappa_estimado": "REAL", "kappa_classificacao": "TEXT",
                "adc_610": "REAL", "adc_680": "REAL", "adc_730": "REAL", "adc_760": "REAL", "adc_810": "REAL", "adc_860": "REAL",
                "ref_610": "REAL", "ref_680": "REAL", "ref_730": "REAL", "ref_760": "REAL", "ref_810": "REAL", "ref_860": "REAL"
            }
            for col_name, col_type in expected_cols.items():
                if col_name not in existing_cols:
                    try:
                        cursor.execute(f"ALTER TABLE leituras_historico ADD COLUMN {col_name} {col_type}")
                    except Exception:
                        pass
            conn.commit()

    def contar_usuarios(self) -> int:
        """Total de usuários cadastrados (usado para o cadastro do primeiro administrador)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM usuarios")
            return cursor.fetchone()[0]

    def validar_login(self, username: str, password: str) -> bool:
        """
        Retorna True se username e senha forem válidos.
        Hashes legados (SHA-256 sem sal) são regravados no formato atual após login correto.
        """
        user = self.obter_usuario(username)
        if not user:
            return False
        ok, needs_rehash = verify_password(password, user["password_hash"])
        if ok and needs_rehash:
            try:
                with self._get_connection() as conn:
                    conn.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?",
                                 (hash_password(password), user["id"]))
            except Exception:
                pass  # a migração é oportunista; o login continua válido
        return ok

    def obter_usuario(self, username: str) -> Optional[Dict]:
        """Obtém dicionário com dados do usuário ou None."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def listar_usuarios(self) -> List[Dict]:
        """Lista todos os usuários cadastrados."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, role FROM usuarios ORDER BY id ASC")
            return [dict(r) for r in cursor.fetchall()]

    def criar_usuario(self, username: str, password: str, role: str = "operador") -> Tuple[bool, str]:
        """Cria um novo usuário."""
        username = username.strip()
        if not username or not password:
            return False, "Usuário e senha não podem ser vazios."
        erro_senha = validate_new_password(password)
        if erro_senha:
            return False, erro_senha
        if role not in ("admin", "operador"):
            return False, "Nível inválido (use 'admin' ou 'operador')."

        pwd_hash = self.hash_password(password)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO usuarios (username, password_hash, role)
                    VALUES (?, ?, ?)
                """, (username, pwd_hash, role))
                conn.commit()
            return True, f"Usuário '{username}' cadastrado com sucesso."
        except sqlite3.IntegrityError:
            return False, f"O usuário '{username}' já existe."
        except Exception as e:
            return False, f"Erro ao criar usuário: {e}"

    def excluir_usuario(self, username: str, current_user: str) -> Tuple[bool, str]:
        """Exclui um usuário com regras de segurança."""
        username = username.strip()
        if username == current_user:
            return False, "Você não pode excluir o usuário atualmente logado."

        target = self.obter_usuario(username)
        if not target:
            return False, "Usuário não encontrado."

        if target["role"] == "admin":
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM usuarios WHERE role = 'admin'")
                admin_count = cursor.fetchone()[0]
                if admin_count <= 1:
                    return False, "Não é permitido excluir o único administrador do sistema."

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM usuarios WHERE username = ?", (username,))
                conn.commit()
            return True, f"Usuário '{username}' excluído com sucesso."
        except Exception as e:
            return False, f"Erro ao excluir: {e}"

    def atualizar_senha(self, username: str, nova_senha: str) -> Tuple[bool, str]:
        """Atualiza a senha de um usuário."""
        if not nova_senha:
            return False, "Nova senha não pode ser vazia."
        erro_senha = validate_new_password(nova_senha)
        if erro_senha:
            return False, erro_senha
        pwd_hash = self.hash_password(nova_senha)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?", (pwd_hash, username))
                conn.commit()
            return True, "Senha alterada com sucesso."
        except Exception as e:
            return False, f"Erro ao atualizar senha: {e}"

    # =========================================================================
    # CRUD - HISTÓRICO COMPLETO DE ENSAIOS ESPECTRAIS
    # =========================================================================

    def inserir_leitura(self, dados: Dict) -> int:
        """
        Insere um ensaio espectral completo na tabela leituras_historico.
        Retorna o id gerado para o registro.
        """
        sql = """
            INSERT INTO leituras_historico (
                codigo_amostra, timestamp, operador, metodo_analitico,
                intensidade_global_adc, pico_espectral_nm, pico_espectral_adc,
                razao_celulose, razao_agua, kappa_estimado, kappa_classificacao,
                adc_610, adc_680, adc_730, adc_760, adc_810, adc_860,
                ref_610, ref_680, ref_730, ref_760, ref_810, ref_860
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
        """
        params = (
            dados.get("codigo_amostra", "AM-0001"),
            dados.get("timestamp", ""),
            dados.get("operador", "Operador"),
            dados.get("metodo_analitico", "Modo Seco"),
            int(dados.get("intensidade_global_adc", 0)),
            int(dados.get("pico_espectral_nm", 610)),
            int(dados.get("pico_espectral_adc", 0)),
            float(dados.get("razao_celulose", 0.0)),
            float(dados.get("razao_agua", 0.0)),
            float(dados.get("kappa_estimado", 0.0)),
            dados.get("kappa_classificacao", "Indeterminado"),
            float(dados.get("adc_610", 0.0)),
            float(dados.get("adc_680", 0.0)),
            float(dados.get("adc_730", 0.0)),
            float(dados.get("adc_760", 0.0)),
            float(dados.get("adc_810", 0.0)),
            float(dados.get("adc_860", 0.0)),
            float(dados.get("ref_610", 0.0)),
            float(dados.get("ref_680", 0.0)),
            float(dados.get("ref_730", 0.0)),
            float(dados.get("ref_760", 0.0)),
            float(dados.get("ref_810", 0.0)),
            float(dados.get("ref_860", 0.0))
        )
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            leitura_id=cursor.lastrowid
            cursor.execute("UPDATE leituras_historico SET calibration_id=?, calibration_snapshot=?, acquisition_count=?, raw_scans_json=? WHERE id=?",
                (dados.get("calibration_id"),dados.get("calibration_snapshot"),
                 dados.get("acquisition_count"),dados.get("raw_scans_json"),leitura_id))
            cursor.execute("UPDATE leituras_historico SET origin=?, trial_context_json=? WHERE id=?",
                           (dados.get("origin", "NAO_CONFIRMADA"), dados.get("trial_context_json", "{}"), leitura_id))
            conn.commit()
            return leitura_id

    def listar_leituras(self, filtro: Optional[str] = None) -> List[Dict]:
        """
        Retorna a lista de leituras registradas, ordenadas da mais recente para a mais antiga.
        Se filtro for fornecido, pesquisa por código de amostra, operador ou data.
        """
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if filtro and filtro.strip():
                termo = f"%{filtro.strip()}%"
                cursor.execute("""
                    SELECT * FROM leituras_historico
                    WHERE codigo_amostra LIKE ? OR operador LIKE ? OR timestamp LIKE ? OR metodo_analitico LIKE ?
                    ORDER BY id DESC
                """, (termo, termo, termo, termo))
            else:
                cursor.execute("SELECT * FROM leituras_historico ORDER BY id DESC")
            return [dict(r) for r in cursor.fetchall()]

    def obter_leitura_por_id(self, leitura_id: int) -> Optional[Dict]:
        """Retorna uma leitura específica pelo seu ID primário."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM leituras_historico WHERE id = ?", (leitura_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def excluir_leitura(self, leitura_id: int) -> bool:
        """Legacy API deliberately refuses permanent deletion. Use invalidar_leitura."""
        raise PermissionError("Exclusão permanente desativada; invalide com autor e motivo.")

    def invalidar_leitura(self, leitura_id: int, actor_id: int, reason: str) -> bool:
        """Enforces permission and records invalidation atomically, retaining the original data."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Motivo obrigatório.")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            actor = conn.execute("SELECT username, role FROM usuarios WHERE id=?", (actor_id,)).fetchone()
            if not actor or actor[1] != "admin":
                raise PermissionError("Somente administrador autenticado pode invalidar ensaios.")
            changed = conn.execute("UPDATE leituras_historico SET invalidated_at=?, invalidated_by=?, invalidation_reason=? WHERE id=? AND invalidated_at IS NULL",
                                   (now, actor[0], reason.strip(), leitura_id)).rowcount
            if changed:
                conn.execute("INSERT INTO audit_events(reading_id, actor, action, reason, timestamp) VALUES(?, ?, 'INVALIDAR', ?, ?)",
                             (leitura_id, actor[0], reason.strip(), now))
            return bool(changed)
