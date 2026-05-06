from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from database import db, Usuario, Lead, Visita, Tarea, Plantilla, Propietario, PropiedadCaptada
from datetime import datetime, timedelta
from functools import wraps
import os
import pytz

ZONA = pytz.timezone("America/Argentina/Buenos_Aires")

def ahora_argentina():
    return datetime.now(pytz.utc).astimezone(ZONA).replace(tzinfo=None)

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from database import db, Usuario, Lead, Visita, Tarea, Plantilla, Propietario, PropiedadCaptada
from datetime import datetime, timedelta
from functools import wraps
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///crm_saas.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'saas-crm-secret-2024')

ADMIN_EMAIL = 'santiago.inmobiliaria.leads@gmail.com'
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin2024')

db.init_app(app)

with app.app_context():
    db.create_all(checkfirst=True)
    # Crear admin si no existe
    admin = Usuario.query.filter_by(email=ADMIN_EMAIL).first()
    if not admin:
        admin = Usuario(
            email=ADMIN_EMAIL,
            nombre='Santiago',
            plan='premium',
            periodo_prueba=False,
            activo=True,
            es_admin=True
        )
        admin.set_password(ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()

# ── Decoradores ────────────────────────────────────────────
def login_requerido(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if not session.get('usuario_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorador

def admin_requerido(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if not session.get('es_admin'):
            flash('Acceso denegado', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorador

def usuario_actual():
    return Usuario.query.get(session.get('usuario_id'))

# ── Auth ───────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('usuario_id'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        usuario  = Usuario.query.filter_by(email=email).first()
        if usuario and usuario.check_password(password):
            if not usuario.activo:
                flash('Tu cuenta está desactivada. Contactá al administrador.', 'danger')
                return redirect(url_for('login'))
            session['usuario_id'] = usuario.id
            session['es_admin']   = usuario.es_admin
            session['nombre']     = usuario.nombre
            return redirect(url_for('dashboard'))
        flash('Email o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        nombre   = request.form.get('nombre', '').strip()
        plan     = request.form.get('plan', 'basico')

        if Usuario.query.filter_by(email=email).first():
            flash('Ya existe una cuenta con ese email', 'danger')
            return redirect(url_for('registro'))

        usuario = Usuario(
            email          = email,
            nombre         = nombre,
            plan           = plan,
            periodo_prueba = True,
            prueba_expira  = ahora_argentina() + timedelta(days=7),
            activo         = True,
            es_admin       = False
        )
        usuario.set_password(password)
        db.session.add(usuario)
        db.session.commit()

        session['usuario_id'] = usuario.id
        session['es_admin']   = False
        session['nombre']     = usuario.nombre
        flash(f'Bienvenido {nombre}! Tenés 7 días de prueba gratis.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('registro.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── Dashboard ──────────────────────────────────────────────
@app.route('/')
@login_requerido
def dashboard():
    u     = usuario_actual()
    hoy   = ahora_argentina().date()
    ahora = ahora_argentina()

    tareas_hoy = Tarea.query.filter(
        Tarea.usuario_id == u.id,
        Tarea.fecha_programada == hoy,
        Tarea.estado == 'pendiente'
    ).all()

    tareas_proximas = Tarea.query.filter(
        Tarea.usuario_id == u.id,
        Tarea.fecha_programada > hoy,
        Tarea.fecha_programada <= hoy + timedelta(days=7),
        Tarea.estado == 'pendiente'
    ).order_by(Tarea.fecha_programada).all()

    visitas_agendadas = Visita.query.filter(
        Visita.usuario_id == u.id,
        Visita.realizada == False,
        Visita.fecha_hora >= ahora
    ).order_by(Visita.fecha_hora).all()

    visitas_sin_confirmar = Visita.query.filter(
        Visita.usuario_id == u.id,
        Visita.realizada == False,
        Visita.fecha_hora < ahora
    ).order_by(Visita.fecha_hora.desc()).all()

    # Recordatorios 2hs antes de visita
    dos_horas = ahora + timedelta(hours=2)
    visitas_recordatorio = Visita.query.filter(
        Visita.usuario_id == u.id,
        Visita.realizada == False,
        Visita.fecha_hora >= ahora,
        Visita.fecha_hora <= dos_horas
    ).order_by(Visita.fecha_hora).all()

    # Plantilla recordatorio
    plantilla_recordatorio = Plantilla.query.filter_by(usuario_id=u.id, tipo='recordatorio_visita').first()
    if not plantilla_recordatorio:
        d = Plantilla.DEFAULTS['recordatorio_visita']
        plantilla_recordatorio = Plantilla(usuario_id=u.id, tipo='recordatorio_visita', nombre=d['nombre'], texto=d['texto'])
        db.session.add(plantilla_recordatorio)
        db.session.commit()

    # Reporte lunes
    es_lunes = ahora.weekday() == 0
    propietarios_reporte = []
    plantilla_reporte = None
    if es_lunes:
        propietarios_reporte = Propietario.query.filter_by(usuario_id=u.id).all()
        plantilla_reporte = Plantilla.query.filter_by(usuario_id=u.id, tipo='reporte_semanal').first()
        if not plantilla_reporte:
            d = Plantilla.DEFAULTS['reporte_semanal']
            plantilla_reporte = Plantilla(usuario_id=u.id, tipo='reporte_semanal', nombre=d['nombre'], texto=d['texto'])
            db.session.add(plantilla_reporte)
            db.session.commit()

    total_leads     = Lead.query.filter_by(usuario_id=u.id).count()
    leads_calientes = Lead.query.filter_by(usuario_id=u.id, temperatura='caliente').count()
    tareas_pend     = Tarea.query.filter_by(usuario_id=u.id, estado='pendiente').count()
    leads_cerrados  = Lead.query.filter_by(usuario_id=u.id, estado='cerrado').count()

    return render_template('dashboard.html',
        usuario=u,
        tareas_hoy=tareas_hoy,
        tareas_proximas=tareas_proximas,
        visitas_agendadas=visitas_agendadas,
        visitas_sin_confirmar=visitas_sin_confirmar,
        visitas_recordatorio=visitas_recordatorio,
        plantilla_recordatorio=plantilla_recordatorio,
        es_lunes=es_lunes,
        propietarios_reporte=propietarios_reporte,
        plantilla_reporte=plantilla_reporte,
        total_leads=total_leads,
        leads_calientes=leads_calientes,
        tareas_pendientes=tareas_pend,
        leads_cerrados=leads_cerrados,
        hoy=hoy, ahora=ahora
    )

# ── Leads ──────────────────────────────────────────────────
@app.route('/leads')
@login_requerido
def leads():
    u = usuario_actual()
    estado_filtro = request.args.get('estado', '')
    temp_filtro   = request.args.get('temperatura', '')
    busqueda      = request.args.get('q', '')

    query = Lead.query.filter_by(usuario_id=u.id)
    if estado_filtro:
        query = query.filter_by(estado=estado_filtro)
    if temp_filtro:
        query = query.filter_by(temperatura=temp_filtro)
    if busqueda:
        query = query.filter(
            db.or_(Lead.nombre.ilike(f'%{busqueda}%'), Lead.telefono.ilike(f'%{busqueda}%'))
        )
    leads = query.order_by(Lead.ultimo_contacto.desc()).all()
    return render_template('leads.html', leads=leads, usuario=u,
                           estado_filtro=estado_filtro, temp_filtro=temp_filtro, busqueda=busqueda)

@app.route('/leads/nuevo', methods=['GET', 'POST'])
@login_requerido
def nuevo_lead():
    u = usuario_actual()
    puede, msg = u.puede_crear_lead
    if not puede:
        flash(msg, 'danger')
        return redirect(url_for('leads'))
    if request.method == 'POST':
        lead = Lead(
            usuario_id      = u.id,
            nombre          = request.form['nombre'],
            telefono        = request.form['telefono'],
            estado          = request.form['estado'],
            temperatura     = request.form['temperatura'],
            notas           = request.form.get('notas', ''),
            ultimo_contacto = ahora_argentina()
        )
        db.session.add(lead)
        db.session.commit()
        flash(f'Lead {lead.nombre} creado', 'success')
        return redirect(url_for('leads'))
    return render_template('form_lead.html', lead=None, accion='Nuevo', usuario=u)

@app.route('/leads/<int:id>')
@login_requerido
def ver_lead(id):
    u    = usuario_actual()
    lead = Lead.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    visitas = Visita.query.filter_by(lead_id=id, usuario_id=u.id).order_by(Visita.fecha_hora.desc()).all()
    tareas  = Tarea.query.filter_by(lead_id=id, usuario_id=u.id).order_by(Tarea.fecha_programada).all()
    return render_template('ver_lead.html', lead=lead, visitas=visitas, tareas=tareas, usuario=u, ahora=ahora_argentina())

@app.route('/leads/<int:id>/editar', methods=['GET', 'POST'])
@login_requerido
def editar_lead(id):
    u    = usuario_actual()
    lead = Lead.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    if request.method == 'POST':
        lead.nombre      = request.form['nombre']
        lead.telefono    = request.form['telefono']
        lead.estado      = request.form['estado']
        lead.temperatura = request.form['temperatura']
        lead.notas       = request.form.get('notas', '')
        lead.ultimo_contacto = ahora_argentina()
        db.session.commit()
        flash('Lead actualizado', 'success')
        return redirect(url_for('ver_lead', id=lead.id))
    return render_template('form_lead.html', lead=lead, accion='Editar', usuario=u)

@app.route('/leads/<int:id>/eliminar', methods=['POST'])
@login_requerido
def eliminar_lead(id):
    u    = usuario_actual()
    lead = Lead.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    db.session.delete(lead)
    db.session.commit()
    flash('Lead eliminado', 'info')
    return redirect(url_for('leads'))

@app.route('/leads/<int:id>/estado', methods=['POST'])
@login_requerido
def cambiar_estado(id):
    u    = usuario_actual()
    lead = Lead.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    lead.estado = request.form['estado']
    db.session.commit()
    return jsonify({'ok': True})

# ── Visitas ────────────────────────────────────────────────
@app.route('/leads/<int:lead_id>/visita/nueva', methods=['GET', 'POST'])
@login_requerido
def nueva_visita(lead_id):
    u    = usuario_actual()
    lead = Lead.query.filter_by(id=lead_id, usuario_id=u.id).first_or_404()
    if request.method == 'POST':
        fecha_hora = datetime.strptime(request.form['fecha_hora'], '%Y-%m-%dT%H:%M')
        es_futura  = fecha_hora > ahora_argentina()
        visita = Visita(
            usuario_id = u.id,
            lead_id    = lead_id,
            propiedad  = request.form['propiedad'],
            fecha_hora = fecha_hora,
            notas      = request.form.get('notas', ''),
            resultado  = '',
            realizada  = not es_futura
        )
        db.session.add(visita)
        db.session.flush()
        if not es_futura:
            generar_tareas(visita, lead, u)
            flash('Visita registrada y seguimientos generados', 'success')
        else:
            flash(f'Visita agendada para el {fecha_hora.strftime("%d/%m/%Y a las %H:%M")}', 'success')
        lead.ultimo_contacto = ahora_argentina()
        db.session.commit()
        return redirect(url_for('ver_lead', id=lead_id))
    return render_template('form_visita.html', lead=lead, usuario=u)

@app.route('/visitas/<int:id>/confirmar', methods=['POST'])
@login_requerido
def confirmar_visita(id):
    u      = usuario_actual()
    visita = Visita.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    accion = request.form.get('accion', 'realizada')

    if accion == 'realizada':
        visita.realizada = True
        visita.resultado = request.form.get('resultado', '')
        generar_tareas(visita, visita.lead, u)
        visita.lead.ultimo_contacto = ahora_argentina()
        db.session.commit()
        flash('Visita confirmada. Seguimientos generados.', 'success')
    elif accion == 'reagendar':
        nueva = request.form.get('nueva_fecha_hora')
        if nueva:
            visita.fecha_hora = datetime.strptime(nueva, '%Y-%m-%dT%H:%M')
            visita.realizada  = False
            db.session.commit()
            flash('Visita reagendada', 'info')
    elif accion == 'cancelar':
        db.session.delete(visita)
        db.session.commit()
        flash('Visita cancelada', 'info')

    return redirect(request.referrer or url_for('dashboard'))

def generar_tareas(visita, lead, usuario):
    base = visita.fecha_hora.date()
    tipos = [
        (1,  'seguimiento_1'),
        (3,  'micro_contacto'),
        (5,  'seguimiento_2'),
        (10, 'cierre'),
    ]
    for dias, tipo in tipos:
        p = Plantilla.query.filter_by(usuario_id=usuario.id, tipo=tipo).first()
        if p:
            texto = p.texto.replace('{nombre}', lead.nombre).replace('{propiedad}', visita.propiedad)
        else:
            d = Plantilla.DEFAULTS.get(tipo, {})
            texto = d.get('texto', '').replace('{nombre}', lead.nombre).replace('{propiedad}', visita.propiedad)

        tarea = Tarea(
            usuario_id       = usuario.id,
            lead_id          = lead.id,
            visita_id        = visita.id,
            fecha_programada = base + timedelta(days=dias),
            tipo             = tipo,
            mensaje_sugerido = texto,
            estado           = 'pendiente'
        )
        db.session.add(tarea)

# ── Tareas ─────────────────────────────────────────────────
@app.route('/tareas/<int:id>/completar', methods=['POST'])
@login_requerido
def completar_tarea(id):
    u     = usuario_actual()
    tarea = Tarea.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    tarea.estado        = 'completado'
    tarea.completado_en = ahora_argentina()
    tarea.lead.ultimo_contacto = ahora_argentina()
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/tareas/<int:id>/reprogramar', methods=['POST'])
@login_requerido
def reprogramar_tarea(id):
    u     = usuario_actual()
    tarea = Tarea.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    dias  = int(request.form.get('dias', 1))
    tarea.fecha_programada = tarea.fecha_programada + timedelta(days=dias)
    tarea.estado = 'pendiente'
    db.session.commit()
    flash('Tarea reprogramada', 'info')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/tareas/<int:id>/cambiar-fecha', methods=['POST'])
@login_requerido
def cambiar_fecha_tarea(id):
    u     = usuario_actual()
    tarea = Tarea.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    nueva = request.form.get('nueva_fecha')
    if nueva:
        tarea.fecha_programada = datetime.strptime(nueva, '%Y-%m-%d').date()
        tarea.estado = 'pendiente'
        db.session.commit()
    return jsonify({'ok': True})

@app.route('/tareas/<int:id>/mensaje', methods=['POST'])
@login_requerido
def guardar_mensaje(id):
    u     = usuario_actual()
    tarea = Tarea.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    tarea.mensaje_sugerido = request.form['mensaje']
    db.session.commit()
    return jsonify({'ok': True})

# ── Kanban ─────────────────────────────────────────────────
@app.route('/kanban')
@login_requerido
def kanban():
    u      = usuario_actual()
    estados = ['nuevo','contactado','visito','interesado','negociacion','frio','cerrado']
    leads_por_estado = {e: Lead.query.filter_by(usuario_id=u.id, estado=e).all() for e in estados}
    return render_template('kanban.html', leads_por_estado=leads_por_estado, estados=estados, usuario=u)

# ── Plantillas ─────────────────────────────────────────────
@app.route('/plantillas')
@login_requerido
def plantillas():
    u     = usuario_actual()
    tipos = ['seguimiento_1','micro_contacto','seguimiento_2','cierre',
             'captacion_inicio','captacion_seguimiento','reporte_semanal','recordatorio_visita']
    plants = []
    for tipo in tipos:
        p = Plantilla.query.filter_by(usuario_id=u.id, tipo=tipo).first()
        if not p:
            d = Plantilla.DEFAULTS[tipo]
            p = Plantilla(usuario_id=u.id, tipo=tipo, nombre=d['nombre'], texto=d['texto'])
            db.session.add(p)
            db.session.commit()
        plants.append(p)
    return render_template('plantillas.html', plantillas=plants, usuario=u)

@app.route('/plantillas/<int:id>/editar', methods=['POST'])
@login_requerido
def editar_plantilla(id):
    u = usuario_actual()
    p = Plantilla.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    p.texto = request.form['texto']
    db.session.commit()
    flash('Plantilla guardada', 'success')
    return redirect(url_for('plantillas'))

@app.route('/plantillas/<int:id>/reset', methods=['POST'])
@login_requerido
def reset_plantilla(id):
    u = usuario_actual()
    p = Plantilla.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    p.texto = Plantilla.DEFAULTS[p.tipo]['texto']
    db.session.commit()
    flash('Plantilla restaurada', 'info')
    return redirect(url_for('plantillas'))

# ── Mi Cuenta ──────────────────────────────────────────────
@app.route('/mi-cuenta', methods=['GET', 'POST'])
@login_requerido
def mi_cuenta():
    u = usuario_actual()
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'cambiar_password':
            actual = request.form.get('password_actual')
            nueva  = request.form.get('password_nueva')
            if u.check_password(actual):
                u.set_password(nueva)
                db.session.commit()
                flash('Contraseña actualizada', 'success')
            else:
                flash('La contraseña actual es incorrecta', 'danger')
        elif accion == 'cambiar_plan':
            nuevo_plan = request.form.get('plan')
            if nuevo_plan in Usuario.PLANES:
                u.plan = nuevo_plan
                db.session.commit()
                flash(f'Plan cambiado a {u.plan_nombre}', 'success')
    return render_template('mi_cuenta.html', usuario=u)

# ── Admin ──────────────────────────────────────────────────
@app.route('/admin')
@login_requerido
@admin_requerido
def admin():
    usuarios = Usuario.query.filter_by(es_admin=False).order_by(Usuario.creado_en.desc()).all()
    return render_template('admin.html', usuarios=usuarios, usuario=usuario_actual())

@app.route('/admin/usuario/<int:id>/toggle', methods=['POST'])
@login_requerido
@admin_requerido
def toggle_usuario(id):
    u = Usuario.query.get_or_404(id)
    u.activo = not u.activo
    db.session.commit()
    estado = 'activado' if u.activo else 'desactivado'
    flash(f'Usuario {u.nombre} {estado}', 'info')
    return redirect(url_for('admin'))

@app.route('/admin/usuario/<int:id>/plan', methods=['POST'])
@login_requerido
@admin_requerido
def cambiar_plan_admin(id):
    u    = Usuario.query.get_or_404(id)
    plan = request.form.get('plan')
    if plan in Usuario.PLANES:
        u.plan = plan
        u.periodo_prueba = False
        db.session.commit()
        flash(f'Plan de {u.nombre} cambiado a {u.plan_nombre}', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/usuario/<int:id>/eliminar', methods=['POST'])
@login_requerido
@admin_requerido
def eliminar_usuario(id):
    u = Usuario.query.get_or_404(id)
    db.session.delete(u)
    db.session.commit()
    flash('Usuario eliminado', 'info')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)

# ── Propietarios / Captaciones ─────────────────────────────
@app.route('/captaciones')
@login_requerido
def captaciones():
    u = usuario_actual()
    propietarios = Propietario.query.filter_by(usuario_id=u.id).order_by(Propietario.ultimo_contacto.desc()).all()
    return render_template('captaciones.html', propietarios=propietarios, usuario=u)

@app.route('/captaciones/nuevo', methods=['GET', 'POST'])
@login_requerido
def nuevo_propietario():
    u = usuario_actual()
    if request.method == 'POST':
        prop = Propietario(
            usuario_id      = u.id,
            nombre          = request.form['nombre'],
            telefono        = request.form['telefono'],
            notas           = request.form.get('notas', ''),
            ultimo_contacto = ahora_argentina()
        )
        db.session.add(prop)
        db.session.flush()

        # Agregar primera propiedad si la pusieron
        if request.form.get('direccion'):
            propiedad = PropiedadCaptada(
                usuario_id     = u.id,
                propietario_id = prop.id,
                direccion      = request.form['direccion'],
                tipo           = request.form.get('tipo', ''),
                precio         = request.form.get('precio', ''),
                estado         = 'captada',
                notas          = request.form.get('notas_propiedad', '')
            )
            db.session.add(propiedad)

        db.session.commit()
        flash(f'Propietario {prop.nombre} agregado', 'success')
        return redirect(url_for('ver_propietario', id=prop.id))
    return render_template('form_propietario.html', propietario=None, usuario=u)

@app.route('/captaciones/<int:id>')
@login_requerido
def ver_propietario(id):
    u    = usuario_actual()
    prop = Propietario.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    plantilla_reporte = Plantilla.query.filter_by(usuario_id=u.id, tipo='reporte_semanal').first()
    if not plantilla_reporte:
        d = Plantilla.DEFAULTS['reporte_semanal']
        plantilla_reporte = Plantilla(usuario_id=u.id, tipo='reporte_semanal', nombre=d['nombre'], texto=d['texto'])
        db.session.add(plantilla_reporte)
        db.session.commit()
    return render_template('ver_propietario.html', propietario=prop, usuario=u,
                           ahora=ahora_argentina(), plantilla_reporte_texto=plantilla_reporte.texto)

@app.route('/captaciones/<int:id>/editar', methods=['GET', 'POST'])
@login_requerido
def editar_propietario(id):
    u    = usuario_actual()
    prop = Propietario.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    if request.method == 'POST':
        prop.nombre          = request.form['nombre']
        prop.telefono        = request.form['telefono']
        prop.notas           = request.form.get('notas', '')
        prop.ultimo_contacto = ahora_argentina()
        db.session.commit()
        flash('Propietario actualizado', 'success')
        return redirect(url_for('ver_propietario', id=prop.id))
    return render_template('form_propietario.html', propietario=prop, usuario=u)

@app.route('/captaciones/<int:id>/eliminar', methods=['POST'])
@login_requerido
def eliminar_propietario(id):
    u    = usuario_actual()
    prop = Propietario.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    db.session.delete(prop)
    db.session.commit()
    flash('Propietario eliminado', 'info')
    return redirect(url_for('captaciones'))

@app.route('/captaciones/<int:prop_id>/propiedad/nueva', methods=['POST'])
@login_requerido
def nueva_propiedad(prop_id):
    u    = usuario_actual()
    prop = Propietario.query.filter_by(id=prop_id, usuario_id=u.id).first_or_404()
    propiedad = PropiedadCaptada(
        usuario_id     = u.id,
        propietario_id = prop_id,
        direccion      = request.form['direccion'],
        tipo           = request.form.get('tipo', ''),
        precio         = request.form.get('precio', ''),
        estado         = 'captada',
        notas          = request.form.get('notas_propiedad', '')
    )
    db.session.add(propiedad)
    db.session.commit()
    flash('Propiedad agregada', 'success')
    return redirect(url_for('ver_propietario', id=prop_id))

@app.route('/propiedad/<int:id>/estado', methods=['POST'])
@login_requerido
def cambiar_estado_propiedad(id):
    u         = usuario_actual()
    propiedad = PropiedadCaptada.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    propiedad.estado = request.form['estado']
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/propiedad/<int:id>/visitas', methods=['POST'])
@login_requerido
def actualizar_visitas_propiedad(id):
    u         = usuario_actual()
    propiedad = PropiedadCaptada.query.filter_by(id=id, usuario_id=u.id).first_or_404()
    propiedad.visitas_count  = int(request.form.get('visitas_count', 0))
    propiedad.ultimo_reporte = ahora_argentina()
    db.session.commit()
    flash('Estadísticas actualizadas', 'success')
    return redirect(url_for('ver_propietario', id=propiedad.propietario_id))
