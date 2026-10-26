"""Professional experimental reports, with measured data and calibration traceability."""
import datetime
import hashlib
import io
import json
import math
import statistics
import sys
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xml.sax.saxutils import escape

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
from chemometrics import classify_experimental_kappa
from version import __version__, __build__

NAVY = '#192F39'
TEAL = '#087D7B'
MUTED = '#62747E'
SOFT = '#E5F3F0'
BORDER = '#D9E2ED'
WAVELENGTHS = [610, 680, 730, 760, 810, 860]
MISSING = 'Não informado'


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _vector(values):
    data = list(values) if values is not None else []
    return [_number(data[i]) if i < len(data) else None for i in range(6)]


def _fmt(value, decimals=2, suffix=''):
    number = _number(value)
    return f'{number:,.{decimals}f}'.replace(',', '_').replace('.', ',').replace('_', '.') + suffix if number is not None else MISSING


def _text(value):
    return escape(str(value)) if value is not None and str(value).strip() else MISSING


def generate_pdf_report(filename, sample_id=None, operator=None, kappa_value=None,
                        operational_mode='seco', kappa_status=None, values=None,
                        raw_adc_values=None, ratio_celulose=None, ratio_agua=None,
                        global_intensity_adc=None, peak_wavelength_nm=None,
                        peak_intensity_adc=None, com_port=None, timestamp=None,
                        material_name=None, match_percentage=None,
                        calibration_snapshot=None, acquisition_count=0, raw_scans=None, trial_context=None):
    """Keep the public API; historical records never inherit today's reference."""
    kappa_status = classify_experimental_kappa(float(kappa_value))[0] if _number(kappa_value) is not None else MISSING
    reference = calibration_snapshot or {}
    trial_context = trial_context or {}
    refs = _vector(values)
    adc = _vector(raw_adc_values)
    white = _vector(reference.get('vetor_branco'))
    dark = _vector(reference.get('vetor_escuro'))
    scans = [_vector(row) for row in (raw_scans or [])]
    scans = [row for row in scans if all(value is not None for value in row)]
    issued = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-4)))
    emitted = issued.strftime('%d/%m/%Y %H:%M:%S') + ' (UTC-04:00)'
    mode = 'Amostra seca / reflectância difusa' if operational_mode == 'seco' else 'Suspensão aquosa / lâmina e lamínula'
    identity = json.dumps([sample_id, timestamp, operator, operational_mode, refs, adc,
                           reference.get('calibration_id'), kappa_value, scans], ensure_ascii=False, default=str)
    report_id = 'SL-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12].upper()
    count = int(acquisition_count or len(scans))
    registered = reference.get('is_calibrated') is True and bool(reference.get('calibration_id'))
    calibration_label = 'Referência registrada no ensaio' if registered else 'Rastreabilidade incompleta'
    if global_intensity_adc is None and all(v is not None for v in adc):
        global_intensity_adc = sum(adc)
    if peak_wavelength_nm is None and all(v is not None for v in adc):
        index = adc.index(max(adc)); peak_wavelength_nm = WAVELENGTHS[index]; peak_intensity_adc = adc[index]

    doc = SimpleDocTemplate(str(filename), pagesize=A4, leftMargin=42, rightMargin=42,
                            topMargin=52, bottomMargin=48, title='Relatório experimental de leitura espectral - ' + str(sample_id or MISSING),
                            author='SPECTRUM-LAB PRO', subject='Caracterização espectral e rastreabilidade instrumental')
    width = doc.width
    font_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / 'fonts'
    regular, bold = 'Helvetica', 'Helvetica-Bold'
    if (font_root / 'Inter-Regular.ttf').is_file() and (font_root / 'Inter-Bold.ttf').is_file():
        pdfmetrics.registerFont(TTFont('SpectrumInter', str(font_root / 'Inter-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('SpectrumInterBold', str(font_root / 'Inter-Bold.ttf')))
        regular, bold = 'SpectrumInter', 'SpectrumInterBold'

    body = ParagraphStyle('Body', fontName=regular, fontSize=9, leading=13, textColor=colors.HexColor(NAVY))
    small = ParagraphStyle('Small', parent=body, fontSize=7.7, leading=10.5, textColor=colors.HexColor(MUTED))
    heading = ParagraphStyle('Heading', parent=body, fontName=bold, fontSize=11, leading=15,
                             spaceBefore=10, spaceAfter=6, keepWithNext=True)
    title = ParagraphStyle('Title', parent=body, fontName=bold, fontSize=24, leading=29, spaceAfter=5)
    label = ParagraphStyle('Label', parent=small, fontName=bold, fontSize=7.2, leading=10)
    table_head = ParagraphStyle('TableHead', parent=small, fontName=bold, textColor=colors.white)
    result = ParagraphStyle('Result', parent=body, fontName=bold, fontSize=30, leading=37, textColor=colors.HexColor(TEAL))
    def p(text, style=body):
        return Paragraph(text, style)
    def section(text):
        return p(text, heading)
    def table(headers, rows, widths):
        data = [[p(_text(x), table_head) for x in headers]] + [[p(_text(x), small) for x in row] for row in rows]
        out = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
        out.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(NAVY)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F5F7')]),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor(TEAL)),
            ('LINEBELOW', (0, 1), (-1, -1), .3, colors.HexColor(BORDER)),
            ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        return out
    def cards(items, columns=2):
        cells = [p(f'<font color="{MUTED}" size="7.2"><b>{_text(name).upper()}</b></font><br/>{_text(value)}') for name, value in items]
        while len(cells) % columns:
            cells.append('')
        grid = Table([cells[i:i+columns] for i in range(0, len(cells), columns)], colWidths=[width/columns]*columns)
        grid.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F2F5F7')),
            ('LINEBELOW', (0, 0), (-1, -1), .4, colors.white),
            ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        return grid
    def chrome(c, document):
        c.saveState()
        pw, ph = A4
        c.setFillColor(colors.HexColor(TEAL)); c.rect(0, ph-8, pw, 8, fill=1, stroke=0)
        c.setFillColor(colors.HexColor(NAVY)); c.setFont('Helvetica-Bold', 9)
        c.drawString(42, ph-34, 'SPECTRUM-LAB PRO')
        c.setFont('Helvetica', 7); c.setFillColor(colors.HexColor(MUTED))
        c.drawRightString(pw-42, ph-34, report_id)
        c.setStrokeColor(colors.HexColor(BORDER)); c.line(42, 36, pw-42, 36)
        c.drawString(42, 24, f'v{__version__} | Build {__build__} | Documento experimental')
        c.drawRightString(pw-42, 24, f'Página {document.page}')
        c.restoreState()

    story = [p('Relatório experimental<br/>de leitura espectral', title), p('Caracterização espectral e estimativa demonstrativa de Kappa', body), Spacer(1, 8)]
    story.append(p('Origem: ' + _text(trial_context.get('origin', 'NAO_CONFIRMADA')), heading))
    invalidation = trial_context.get('invalidation')
    if invalidation:
        story.append(p('REGISTRO INVALIDADO: ' + _text(invalidation.get('reason')) + ' / ' + _text(invalidation.get('by')) + ' / ' + _text(invalidation.get('at')), heading))
    device = trial_context.get('device') or {}
    story.append(cards([('ID do ensaio', trial_context.get('trial_id')),
                        ('Início (UTC)', trial_context.get('started_at')),
                        ('Bancada', device.get('device_id')), ('Firmware / protocolo', str(device.get('firmware', MISSING)) + ' / ' + str(device.get('protocol', MISSING)))]))
    story.append(p('Resultado principal calculado da média espectral; estimativa demonstrativa sem validação analítica.', small))
    story.append(cards([('Amostra', sample_id), ('Operador', operator), ('Data da medição', timestamp), ('Método operacional', mode)]))
    story.append(section('01  /  Resultado do ensaio'))
    result_card = Table([[p('KAPPA DEMONSTRATIVO', label), p('FAIXA DO MODELO EXPERIMENTAL', label)],
                         [p(_fmt(kappa_value), result), p(_text(kappa_status), body)]], colWidths=[width*.34, width*.66])
    result_card.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor(SOFT)),
                                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                                    ('LEFTPADDING', (0,0), (-1,-1), 14), ('RIGHTPADDING', (0,0), (-1,-1), 14),
                                    ('TOPPADDING', (0,0), (-1,-1), 9), ('BOTTOMPADDING', (0,0), (-1,-1), 9)]))
    story += [result_card, Spacer(1, 7), p('Estimativa por equações parametrizadas, sem validação analítica. A faixa numérica descreve apenas o modelo experimental; não identifica processo industrial nem teor de lignina.', small)]
    story.append(cards([('Razão R680 / R730', _fmt(ratio_celulose, 3)), ('Razão R860 / R760', _fmt(ratio_agua, 3)),
                        ('Soma dos sinais ADC', _fmt(global_intensity_adc, 1, ' ADC')), ('Canal de maior sinal', _fmt(peak_wavelength_nm, 0, ' nm') + (' / ' + _fmt(peak_intensity_adc, 1, ' ADC') if peak_intensity_adc is not None else ''))]))
    story.append(section('02  /  Perfil espectral relativo'))
    fig = Figure(figsize=(7.1, 2.0), dpi=180)
    agg = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.set_facecolor('#F2F5F7')
    heights = [v if v is not None else float('nan') for v in refs]
    ax.bar(range(6), heights, color=TEAL, width=.48, zorder=3)
    ax.set_xticks(range(6), [str(v) for v in WAVELENGTHS])
    ax.set_ylabel('Resposta relativa (%)', fontsize=8, color=NAVY)
    ax.set_xlabel('Comprimento de onda (nm)', fontsize=8, color=MUTED)
    ax.tick_params(labelsize=8, colors=MUTED)
    ax.grid(axis='y', color=BORDER, linewidth=.6, zorder=0)
    for side in ('top', 'right'): ax.spines[side].set_visible(False)
    for side in ('left', 'bottom'): ax.spines[side].set_color(BORDER)
    available = [v for v in refs if v is not None]
    ax.set_ylim(min(0, min(available, default=0)*1.2), max(10, max(available, default=0)*1.25))
    for i, value in enumerate(refs):
        if value is not None: ax.annotate(_fmt(value, 1), (i, value), xytext=(0,5), textcoords='offset points', ha='center', fontsize=8, color=NAVY)
    fig.tight_layout(pad=1.1)
    chart = io.BytesIO(); agg.print_png(chart); chart.seek(0)
    story.append(Image(chart, width=width, height=80))
    story.append(table(['Canal', 'Sinal da amostra (ADC)', 'Resposta relativa (%)'],
                       [[f'{wl} nm', _fmt(adc[i],1), _fmt(refs[i])] for i,wl in enumerate(WAVELENGTHS)], [width*.2,width*.4,width*.4]))
    story += [PageBreak()]
    story += [p('Rastreabilidade', title), p('Referência instrumental, aquisição e condições do ensaio', body), p('ADC: contagens do detector. A resposta é relativa ao branco de trabalho, com correção do escuro; não representa refletância absoluta certificada.', small)]
    story.append(section('03  /  Referência utilizada na medição'))
    story.append(cards([('Registro da referência', calibration_label), ('Referência de trabalho', reference.get('reference_label')),
                        ('Calibração realizada em', reference.get('timestamp')), ('Operador da calibração', reference.get('operador')),
                        ('Identificador da calibração', reference.get('calibration_id')), ('Aquisições da amostra', str(count) if count else MISSING)]))
    settings = reference.get('settings') or {}
    settings_text = ' / '.join([
        'Sensor: ' + str(settings.get('sensor') or MISSING),
        'Ganho: ' + _fmt(settings.get('gain'), 0, 'x'),
        'Integração: ' + _fmt(settings.get('integration_ms'), 1, ' ms'),
        'Corrente LED configurada: ' + _fmt(settings.get('led_ma'), 1, ' mA')])
    story += [Spacer(1, 8), p('<b>Configurações registradas:</b> ' + _text(settings_text), small),
              p('<b>Interface de comunicação:</b> ' + _text(com_port) + '<br/><b>Método do escuro:</b> ' + ('LED desligado' if reference.get('dark_method') == 'led_off' else _text(reference.get('dark_method'))), small)]
    ws, ds = reference.get('white_stats') or {}, reference.get('dark_stats') or {}
    cvs = _vector(ws.get('cv_percent')); noise = _vector(ds.get('stdevs'))
    story += [Spacer(1, 8), table(['Canal', 'Branco (ADC)', 'Escuro (ADC)', 'CV branco (%)', 'DP escuro (ADC)'],
              [[f'{wl} nm', _fmt(white[i],1), _fmt(dark[i],1), _fmt(cvs[i]), _fmt(noise[i])] for i,wl in enumerate(WAVELENGTHS)],
              [width*.14,width*.215,width*.215,width*.215,width*.215]),
              Spacer(1, 6), p(f'Aquisições do branco: {_text(ws.get("n"))} | Aquisições do escuro: {_text(ds.get("n"))}. DP: desvio padrão amostral; CV: coeficiente de variação.', small)]
    story.append(section('04  /  Consistência das aquisições'))
    if len(scans) >= 2:
        rows = []
        for i, wl in enumerate(WAVELENGTHS):
            channel = [row[i] for row in scans]; mean = statistics.mean(channel); sd = statistics.stdev(channel)
            rows.append([f'{wl} nm', _fmt(mean,1), _fmt(sd), _fmt(100*sd/abs(mean)) if mean else 'Não definido'])
        story.append(table(['Canal', 'Média (ADC)', 'DP (ADC)', 'CV (%)'], rows, [width*.22,width*.26,width*.26,width*.26]))
        story.append(p(f'Estatísticas calculadas de {len(scans)} aquisições brutas disponíveis. Descrevem a dispersão do sinal e não a incerteza do Kappa.', small))
    else:
        story.append(p('Aquisições individuais insuficientes ou não disponíveis neste registro; desvio padrão e CV da amostra não foram calculados.', small))
    story.append(section('05  /  Método e limites de interpretação'))
    story.append(p('Correção por canal: resposta relativa (%) = 100 x (amostra - escuro) / (branco - escuro). As razões R680/R730 e R860/R760 são descritores utilizados pelo modelo parametrizado da bancada.', small))
    story.append(p('O Kappa é uma estimativa demonstrativa. Não foram atribuídos R², RMSE ou incerteza analítica sem dados de validação. O resultado não substitui um método de referência. Valores acima de 100% são preservados, pois a amostra pode retornar mais sinal que o branco de trabalho.', small))
    story.append(p('A presença de uma referência registrada não comprova, por si só, sua validade temporal ou a certificação do resultado. Campos sem dados são identificados como não informados. Este documento descreve o registro experimental e não possui validade oficial.', small))
    if reference.get('notes'):
        story.append(p('<b>Observações da calibração:</b> ' + _text(reference['notes']), small))
    story += [Spacer(1, 12), p('<b>Registro do operador:</b> ' + _text(operator) + ' | Documento gerado eletronicamente; sem assinatura digital.', small),
              p('<b>Emissão:</b> ' + emitted, small)]
    doc.build(story, onFirstPage=chrome, onLaterPages=chrome)
    return filename
