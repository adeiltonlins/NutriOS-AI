from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'app'/'static'

def test_dashboard_uses_real_patient_last_access_column():
    s=(ROOT/'app'/'main.py').read_text(encoding='utf-8')
    assert 'id,name,active,access_expires_at,last_access_at,created_at,macro_targets' in s
    assert 'id,name,active,access_expires_at,last_seen_at,created_at,macro_targets' not in s

def test_new_patient_is_explicitly_active():
    s=(ROOT/'app'/'main.py').read_text(encoding='utf-8')
    block=s[s.index('def create_patient('):s.index('@app.patch("/app/api/pacientes/{patient_id}")')]
    assert '"active": True' in block

def test_recent_checkin_opens_patient_diary():
    s=(STATIC/'app.html').read_text(encoding='utf-8')
    assert '#diary' in s and 'x.patient_id' in s
    assert "status:'Concluído',href:'/app/clinica'" not in s

def test_recent_appointment_opens_patient_schedule():
    s=(STATIC/'app.html').read_text(encoding='utf-8')
    assert '#schedule' in s
    assert "status:'Agendado',href:'/app/gestao'" not in s

def test_diary_feedback_no_browser_prompt():
    s=(STATIC/'clinical-suite.js').read_text(encoding='utf-8')
    assert "prompt('Retorno ao paciente:')" not in s
    assert 'Retorno profissional' in s
    assert 'feedbackDialog' in s

def test_assessment_checkbox_is_fixed_size():
    s=(STATIC/'nutrios-v32-clinical-fixes.css').read_text(encoding='utf-8')
    assert '#assessment .assessment-grid .consent input[type="checkbox"]' in s
    assert 'width:20px!important' in s
    assert 'min-width:20px!important' in s
