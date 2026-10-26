"""
SPECTRUM-LAB PRO | Módulo Quimiométrico e Calibração Instrumental
Metodologia: Suspensão aquosa de celulose sob lâmina e lamínula de microscópio.
Sensor: AS7263 NIR (6 canais: 610, 680, 730, 760, 810, 860 nm).

Funcionalidades:
1. Persistência em calibracao.json (vetor_branco, vetor_escuro, metadados).
2. Cálculo de Refletância Relativa (R_i).
3. Normalização Vetorial (pela soma - R_norm).
4. Mapeamento de Eixos Quimiométricos:
   - Eixo X (Fibras de Celulose): R_norm[680 nm] / R_norm[730 nm] (Bandas S/T)
   - Eixo Y (Matriz Aquosa / Espessura): R_norm[860 nm] / R_norm[760 nm] (Bandas W/U)
5. Estatísticas de Repetibilidade (Média, Desvio Padrão Amostral, CV%).
6. Classificação Híbrida e Estimativa de Número Kappa.
"""

import os
import json
import math
import datetime
from typing import List, Tuple, Dict, Any, Optional

import tempfile
from runtime_data import create_json_if_missing
import numpy as np

# Comprimentos de onda dos 6 canais do AS7263
WAVELENGTHS = [610, 680, 730, 760, 810, 860]
CHANNEL_NAMES = ["610nm (R)", "680nm (S)", "730nm (T)", "760nm (U)", "810nm (V)", "860nm (W)"]

# Índices canônicos para as razões de celulose e água:
IDX_680 = 1
IDX_730 = 2
IDX_760 = 3
IDX_860 = 5

DEFAULT_CALIBRATION_FILE = "calibracao.json"

OPERATIONAL_MODES = ["umido", "seco"]
MODE_LABELS = {
    "umido": "Suspensão Aquosa (Lâmina / Água)",
    "seco": "Amostra Seca (Reflectância Difusa)"
}

CALIB_TIMEOUT_OPTIONS = [
    ("1 minuto (Teste Rápido)", 60),
    ("5 minutos (Bancada)", 300),
    ("1 hora", 3600),
    ("8 horas (Turno)", 28800),
    ("24 horas (Padrão)", 86400)
]
DEFAULT_TIMEOUT_SECS = 86400


class ChemometricsEngine:
    """Referenciamento óptico relativo; não valida analiticamente o Kappa."""
    DEFAULT_SETTINGS = {"sensor":"AS7263","gain":64.0,"integration_ms":140.0,"led_ma":50.0}
    REFERENCE_LABEL = "Cartão branco fosco (referência de trabalho não certificada)"
    MIN_REFERENCE_SPAN = 10.0
    MAX_WHITE_CV = 5.0

    def __init__(self, calib_file_path=None):
        if calib_file_path is None:
            base=os.environ.get("SPECTRUM_LAB_DATA_DIR")
            if not base:
                base=(os.path.join(os.environ.get("LOCALAPPDATA",os.path.expanduser("~")),"SpectrumLabPro")
                      if getattr(__import__("sys"),"frozen",False) else os.path.dirname(os.path.abspath(__file__)))
            calib_file_path=os.path.join(base,DEFAULT_CALIBRATION_FILE)
        self.calib_file_path=os.path.abspath(calib_file_path)
        self.active_mode="seco"
        self.timeout_segundos=DEFAULT_TIMEOUT_SECS
        self.last_error=""
        self.calibracoes={m:self._empty_profile(m) for m in OPERATIONAL_MODES}
        self.history=[]
        self._activate()
        self.load_calibration()
        if not os.path.exists(self.calib_file_path):
            try:
                create_json_if_missing(self.calib_file_path, self._json_payload())
            except OSError as err:
                self.last_error = str(err)

    def _empty_profile(self,mode):
        return {"is_calibrated":False,"timestamp":"","operador":"","notes":"",
                "vetor_branco":[],"vetor_escuro":[],"r2":None,"rmse":None,"n_amostras":0,
                "calibration_id":"","dark_method":"","settings":{},"white_stats":{},"dark_stats":{},
                "reference_label":self.REFERENCE_LABEL if mode=="seco" else "Lâmina/lamínula com água destilada"}

    def _activate(self):
        p=self.calibracoes[self.active_mode]
        for attr,key in [("vetor_branco","vetor_branco"),("vetor_escuro","vetor_escuro"),
                         ("is_calibrated","is_calibrated"),("calib_timestamp","timestamp"),
                         ("calib_operador","operador"),("calib_notes","notes"),
                         ("n_amostras","n_amostras"),("calibration_id","calibration_id")]:
            value=p.get(key)
            setattr(self,attr,list(value) if isinstance(value,list) else value)
        self.r2=self.rmse=None

    @staticmethod
    def validate_raw(values,allow_zero=False):
        if values is None or len(values)!=6:
            raise ValueError("A aquisição deve conter seis canais.")
        vec=[float(v) for v in values]
        if any(not math.isfinite(v) or v<0 or v>=65500 for v in vec):
            raise ValueError("Leitura inválida ou saturada; ajuste a óptica/ganho e recalibre.")
        if not allow_zero and not any(v>0 for v in vec):
            raise ValueError("Nenhum sinal óptico detectado.")
        return vec

    def _validate_profile(self,p):
        if p.get("dark_method")!="led_off" or not p.get("calibration_id"):
            raise ValueError("Referência antiga: refaça branco e escuro com o firmware atualizado.")
        white=self.validate_raw(p.get("vetor_branco"))
        dark=self.validate_raw(p.get("vetor_escuro"),allow_zero=True)
        ws,ds=p.get("white_stats",{}),p.get("dark_stats",{})
        if ws.get("n",0)<2 or ds.get("n",0)<2:
            raise ValueError("As referências precisam de múltiplas aquisições.")
        for stat in (ws,ds):
            deviations=stat.get("stdevs",[])
            if len(deviations)!=6 or any(not math.isfinite(float(v)) or v<0 for v in deviations):
                raise ValueError("Estatísticas de referência inválidas.")
        cvs=ws.get("cv_percent",[])
        if len(cvs)!=6 or any(not math.isfinite(v) or v<0 for v in cvs) or max(cvs)>self.MAX_WHITE_CV:
            raise ValueError("Branco instável: CV acima de 5%. Verifique posição e iluminação.")
        for i,(w,d) in enumerate(zip(white,dark)):
            noise=math.hypot(ws["stdevs"][i],ds["stdevs"][i])
            if w-d<=max(self.MIN_REFERENCE_SPAN,5*noise):
                raise ValueError(f"Referência insuficiente no canal {WAVELENGTHS[i]} nm.")
        if p.get("settings")!=self.DEFAULT_SETTINGS:
            raise ValueError("Configurações ópticas incompatíveis.")
        ts=datetime.datetime.strptime(p["timestamp"],"%Y-%m-%d %H:%M:%S")
        if ts>datetime.datetime.now()+datetime.timedelta(seconds=5):
            raise ValueError("Data de calibração está no futuro.")

    def calibration_valid(self):
        try:
            if not self.is_calibrated:
                raise ValueError("Branco e escuro ainda não registrados.")
            self._validate_profile(self.calibracoes[self.active_mode])
            if self.is_calibration_expired():
                raise ValueError("Prazo operacional da referência expirado.")
            self.last_error=""
            return True
        except (ValueError,TypeError,KeyError,OverflowError) as err:
            self.last_error=str(err)
            return False

    def set_mode(self,mode):
        mode=str(mode).strip().lower()
        if mode not in OPERATIONAL_MODES:
            return False
        old=self.active_mode
        self.active_mode=mode
        if not self._save_full_json():
            self.active_mode=old
            return False
        self._activate()
        return True

    def is_calibration_expired(self):
        if not self.is_calibrated or not self.calib_timestamp:
            return True
        try:
            elapsed=(datetime.datetime.now()-datetime.datetime.strptime(self.calib_timestamp,"%Y-%m-%d %H:%M:%S")).total_seconds()
            return elapsed < -5 or elapsed>=self.timeout_segundos
        except (ValueError,TypeError):
            return True

    def get_remaining_validity_seconds(self):
        if self.is_calibration_expired():
            return 0.0
        elapsed=(datetime.datetime.now()-datetime.datetime.strptime(self.calib_timestamp,"%Y-%m-%d %H:%M:%S")).total_seconds()
        return max(0.0,self.timeout_segundos-elapsed)

    def set_timeout_seconds(self,seconds):
        old=self.timeout_segundos
        self.timeout_segundos=max(10,min(86400,int(seconds)))
        if not self._save_full_json():
            self.timeout_segundos=old
            return False
        return True

    def load_calibration(self):
        if not os.path.exists(self.calib_file_path):
            return False
        try:
            with open(self.calib_file_path,encoding="utf-8") as f:
                data=json.load(f)
            loaded={}
            for mode in OPERATIONAL_MODES:
                p=self._empty_profile(mode)
                p.update(data.get("modo_"+mode,{}))
                p["r2"]=p["rmse"]=None
                try:
                    self._validate_profile(p)
                except (ValueError,TypeError,KeyError,OverflowError):
                    p["is_calibrated"]=False
                loaded[mode]=p
            self.calibracoes=loaded
            self.history=data.get("historico_calibracoes",[])
            self.timeout_segundos=max(10,min(86400,int(data.get("timeout_segundos",86400))))
            self.active_mode=data.get("modo_ativo","seco")
            if self.active_mode not in OPERATIONAL_MODES:
                self.active_mode="seco"
            self._activate()
            return True
        except (OSError,ValueError,TypeError,AttributeError) as err:
            self.last_error=str(err)
            self.calibracoes={m:self._empty_profile(m) for m in OPERATIONAL_MODES}
            self.active_mode="seco"
            self._activate()
            return False

    def _json_payload(self,profiles=None,history=None):
        profiles=self.calibracoes if profiles is None else profiles
        payload={"schema_version":2,"modo_ativo":self.active_mode,"timeout_segundos":self.timeout_segundos,
                 "canais_nm":WAVELENGTHS,"historico_calibracoes":self.history if history is None else history}
        payload.update({"modo_"+m:profiles[m] for m in OPERATIONAL_MODES})
        return payload

    def _save_full_json(self,profiles=None,history=None):
        payload=self._json_payload(profiles,history)
        path=None
        try:
            folder=os.path.dirname(self.calib_file_path)
            os.makedirs(folder,exist_ok=True)
            fd,path=tempfile.mkstemp(dir=folder,prefix="calib_",suffix=".tmp")
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                json.dump(payload,f,indent=2,ensure_ascii=False,allow_nan=False)
                f.flush(); os.fsync(f.fileno())
            os.replace(path,self.calib_file_path)
            self.last_error=""
            return True
        except (OSError,ValueError,TypeError) as err:
            self.last_error=str(err)
            if path and os.path.exists(path):
                os.remove(path)
            return False

    def save_calibration(self,vetor_branco=None,vetor_escuro=None,r2=None,rmse=None,
                         n_amostras=None,notes=None,operador=None,*,white_scans=None,
                         dark_scans=None,settings=None,reference_label=None,dark_method="led_off"):
        try:
            if not white_scans or not dark_scans:
                raise ValueError("É obrigatório medir novamente branco e escuro.")
            white_scans=[self.validate_raw(v) for v in white_scans]
            dark_scans=[self.validate_raw(v,allow_zero=True) for v in dark_scans]
            ws=self.compute_repeatability_stats(white_scans)
            ds=self.compute_repeatability_stats(dark_scans)
            p=self._empty_profile(self.active_mode)
            p.update({"vetor_branco":ws["means"],"vetor_escuro":ds["means"],
                      "white_stats":ws,"dark_stats":ds,"white_scans":white_scans,"dark_scans":dark_scans,"is_calibrated":True,
                      "timestamp":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                      "operador":operador or "Operador não identificado",
                      "notes":notes or "Referenciamento relativo: branco + LED desligado",
                      "n_amostras":len(white_scans),"settings":dict(settings or {}),
                      "reference_label":reference_label or p["reference_label"],
                      "dark_method":dark_method,"calibration_id":__import__("uuid").uuid4().hex})
            self._validate_profile(p)
            profiles=__import__("copy").deepcopy(self.calibracoes)
            profiles[self.active_mode]=p
            history=self.history+[{"modo":self.active_mode,**__import__("copy").deepcopy(p)}]
            if not self._save_full_json(profiles,history):
                return False
            self.calibracoes,self.history=profiles,history
            self._activate()
            return True
        except (ValueError,TypeError,KeyError,OverflowError) as err:
            self.last_error=str(err)
            return False

    def snapshot(self):
        return __import__("copy").deepcopy(self.calibracoes[self.active_mode])

    def calculate_regression_metrics(self,y_true,y_pred):
        n=len(y_true)
        if n<2 or len(y_pred)!=n:
            return None,None,n
        mean=sum(y_true)/n; total=sum((y-mean)**2 for y in y_true)
        residual=sum((y-p)**2 for y,p in zip(y_true,y_pred))
        return (1-residual/total if total>0 else None),math.sqrt(residual/n),n

    def calculate_relative_reflectance(self,raw_counts):
        if not self.calibration_valid():
            raise ValueError(self.last_error)
        vec=self.validate_raw(raw_counts)
        p=self.calibracoes[self.active_mode]; out=[]
        for i,(sample,w,d) in enumerate(zip(vec,self.vetor_branco,self.vetor_escuro)):
            signal=sample-d
            if signal<=max(2.0,3*p["dark_stats"]["stdevs"][i]):
                raise ValueError(f"Sinal insuficiente no canal {WAVELENGTHS[i]} nm.")
            out.append(signal/(w-d))
        return out

    @staticmethod
    def normalize_sum(r_vec):
        vec=[float(v) for v in r_vec]
        if len(vec)!=6 or any(not math.isfinite(v) or v<0 for v in vec) or sum(vec)<=0:
            raise ValueError("Espectro inválido para normalização pela soma.")
        return [v/sum(vec) for v in vec]

    # Compatibility only: this operation divides by the sum, never standard normal variate.
    normalize_snv=normalize_sum

    @staticmethod
    def calculate_scatter_ratios(r_norm):
        if len(r_norm)!=6 or any(not math.isfinite(v) or v<=0 for v in r_norm):
            raise ValueError("Espectro insuficiente para razões.")
        return r_norm[IDX_680]/r_norm[IDX_730],r_norm[IDX_860]/r_norm[IDX_760]

    calculate_ratios=calculate_scatter_ratios
    @staticmethod
    def compute_repeatability_stats(scans: List[List[float]]) -> Dict[str, Any]:
        """
        Calcula estatísticas completas de repetibilidade (5 varreduras estáticas):
        Para cada canal i in [0..5]:
        - Média: mu_i
        - Desvio Padrão Amostral: s_i (divisor N - 1)
        - Coeficiente de Variação: CV% = (s_i / mu_i) * 100%
        """
        n = len(scans)
        if n < 2:
            return {
                "n": n,
                "means": scans[0] if n == 1 else [0.0] * 6,
                "stdevs": [0.0] * 6,
                "cv_percent": [0.0] * 6,
                "global_cv_mean": 0.0,
                "is_valid": False
            }

        means = []
        stdevs = []
        cvs = []

        for ch in range(6):
            vals = [float(s[ch]) for s in scans]
            mean_val = sum(vals) / n
            means.append(mean_val)

            # Desvio padrão amostral com Bessel correction (N - 1)
            variance = sum((v - mean_val) ** 2 for v in vals) / (n - 1)
            s_val = math.sqrt(max(0.0, variance))
            stdevs.append(s_val)

            if mean_val > 1e-6:
                cv_val = (s_val / mean_val) * 100.0
            else:
                cv_val = 0.0
            cvs.append(cv_val)

        global_cv = sum(cvs) / 6.0

        return {
            "n": n,
            "means": means,
            "stdevs": stdevs,
            "cv_percent": cvs,
            "global_cv_mean": global_cv,
            "is_valid": True
        }


def calculate_hybrid_similarity(
    sample_vec: List[float],
    ref_vec: List[float],
    calib_engine: Optional[ChemometricsEngine] = None
) -> Tuple[float, bool]:
    """
    Similaridade híbrida entre amostra e espectro de referência do banco:
    Combinação de Cosseno Angular e Distância Euclidiana Normalizada,
    com validação por razões espectrais NIR.
    """
    if len(sample_vec) < 6 or len(ref_vec) < 6:
        return 0.0, False

    # Normalização min-max / SNV para comparação robusta
    sum_s = sum(sample_vec[:6])
    sum_r = sum(ref_vec[:6])

    if sum_s > 0:
        norm_s = [float(s) / sum_s for s in sample_vec[:6]]
    else:
        norm_s = [0.0] * 6

    if sum_r > 0:
        norm_r = [float(r) / sum_r for r in ref_vec[:6]]
    else:
        norm_r = [0.0] * 6

    # 1. Similaridade de Cosseno (Sc)
    dot_prod = sum(s * r for s, r in zip(norm_s, norm_r))
    mag_s = math.sqrt(sum(s * s for s in norm_s))
    mag_r = math.sqrt(sum(r * r for r in norm_r))

    if mag_s == 0.0 or mag_r == 0.0:
        return 0.0, False

    sc = max(0.0, min(1.0, dot_prod / (mag_s * mag_r)))

    # 2. Distância Euclidiana Normalizada (De)
    euclid = math.sqrt(sum((s - r) ** 2 for s, r in zip(norm_s, norm_r)))
    de = min(1.0, euclid / max(1e-6, (mag_s + mag_r)))

    score_base = (0.6 * sc) + (0.4 * (1.0 - de))

    # 3. Validação de Razão de Celulose (R680 / R730)
    r680_s = max(1e-4, norm_s[IDX_680])
    r730_s = max(1e-4, norm_s[IDX_730])
    r680_r = max(1e-4, norm_r[IDX_680])
    r730_r = max(1e-4, norm_r[IDX_730])

    ratio_s = r680_s / r730_s
    ratio_r = r680_r / r730_r
    diff_ratio = abs(ratio_s - ratio_r) / max(1e-4, ratio_r)

    penalized = False
    if diff_ratio > 0.18:
        excess = diff_ratio - 0.18
        penalty = min(0.30, excess * 0.8)
        score_base = max(0.0, score_base - penalty)
        penalized = True

    match_percent = score_base * 100.0
    return match_percent, penalized


def classify_experimental_kappa(value):
    """Numeric bands describe only the experimental model, without process inference."""
    value=float(value)
    if not math.isfinite(value) or value<0:
        return "Faixa não disponível", "#94A3B8"
    for upper,label,color in (
        (2,"Faixa 1 — até 2","#10B981"),
        (6,"Faixa 2 — acima de 2 até 6","#34D399"),
        (12,"Faixa 3 — acima de 6 até 12","#38BDF8"),
        (22,"Faixa 4 — acima de 12 até 22","#F59E0B"),
        (55,"Faixa 5 — acima de 22 até 55","#FB923C")):
        if value<=upper:return label,color
    return "Faixa 6 — acima de 55", "#EF4444"


def calculate_kappa_number(spectral_values: List[float], mode: str = "umido") -> Tuple[float, str, str]:
    """
    Estimativa demonstrativa com coeficientes fixos, sem validação analítica.
    Entrada: seis respostas relativas em fração (1.0 corresponde à referência branca).
    Modo úmido: 14.5*(R860/R680) - 3.2*(R680/R730) + 8.
    Modo seco: 0.5 + 45*max(0,0.8-R610) + 25*max(0,R680/R730-1.2).
    Não usar como determinação de Kappa de referência.
    """
    if not spectral_values or len(spectral_values) < 6:
        return 0.0, "Indeterminado", "#6B7280"

    spectral_values=[float(v) for v in spectral_values]
    if any(not math.isfinite(v) or v<=0 for v in spectral_values):
        raise ValueError("Espectro inválido: Kappa demonstrativo não calculado.")
    r610 = max(0.0001, float(spectral_values[0]))
    r680 = max(0.0001, float(spectral_values[1]))
    r730 = max(0.0001, float(spectral_values[2]))
    r760 = max(0.0001, float(spectral_values[3]))
    r810 = max(0.0001, float(spectral_values[4]))
    r860 = max(0.0001, float(spectral_values[5]))

    # Razões Ópticas Base
    r_cel = r680 / r730
    cellulose_ratio = r_cel
    r_water = r860 / r760
    lignin_ratio = r860 / r680

    if mode == "seco":
        # R610 em porcentagem (0 a 100)
        r610_val = float(spectral_values[0])
        r610_pct = r610_val * 100.0  # entrada exclusivamente em fração

        # Razão Celulose/Lignina (680nm / 730nm)
        r_cel = float(spectral_values[1]) / (float(spectral_values[2]) + 1e-6)

        # Termo de escurecimento: só penaliza se R610 for menor que 80% (amostra escura/marrom)
        fator_escurecimento = max(0.0, (80.0 - r610_pct) / 100.0) * 45.0

        # Termo de lignina residual: só penaliza se r_cel for maior que 1.20
        delta_lignina = max(0.0, (r_cel - 1.20)) * 25.0

        kappa_calc = 0.5 + fator_escurecimento + delta_lignina
        kappa_predito = float(kappa_calc)
    else:
        # Modo 'umido' (Suspensão Aquosa)
        kappa_calc = (lignin_ratio * 14.5) - (cellulose_ratio * 3.2) + 8.0
        kappa_predito = float(kappa_calc)

    # Garante ausência de travas de teto (sem min(..., 50.0)), mantendo apenas proteção contra negativos
    kappa_exibido = max(0.0, float(kappa_predito))

    classificacao, color = classify_experimental_kappa(kappa_exibido)

    return round(kappa_exibido, 2), classificacao, color


# Atribui como método estático em ChemometricsEngine
ChemometricsEngine.calculate_kappa_number = staticmethod(calculate_kappa_number)
