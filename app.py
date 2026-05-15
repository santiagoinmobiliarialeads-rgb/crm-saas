
# ── Notificaciones Push ────────────────────────────────────
import json as json_module
from database import SuscripcionPush

VAPID_PUBLIC_KEY  = os.environ.get('VAPID_PUBLIC_KEY',  'BMWg2b6UbO9o8J2HdRQfeaQZc7y0_6FtKSVCYvJPo9ECQsUGT9ZP5MN2aGkxq2h7M-HOsvjPmfNKR0pTcuB3Ofk')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', 'LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JR0hBZ0VBTUJNR0J5cUdTTTQ5QWdFR0NDcUdTTTQ5QXdFSEJHMHdhd0lCQVFRZys2MnlzdXNQMHVJeU1ObkwKLy8rRWUrZXhuRWJGRUgyR1FvT2kwU0FqUzlPaFJBTkNBQVRGb05tK2xHenZhUENkaDNVVUgzbWtHWE84dFAraApiU2tsUW1MeVQ2UFJBa0xGQmsvV1QrVERkbWhwTWF0b2V6UGh6ckw0ejVuelNrZEtVM0xnZHpuNQotLS0tLUVORCBQUklWQVRFIEtFWS0tLS0tCg')
VAPID_EMAIL = 'mailto:santiago.inmobiliaria.leads@gmail.com'

@app.route('/notificaciones/suscribir', methods=['POST'])
@login_requerido
def suscribir_notificaciones():
    u = usuario_actual()
    data = request.get_json()
    sub_json = json_module.dumps(data)
    existente = SuscripcionPush.query.filter_by(usuario_id=u.id).first()
    if existente:
        existente.subscription_json = sub_json
    else:
        db.session.add(SuscripcionPush(usuario_id=u.id, subscription_json=sub_json))
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/notificaciones/verificar')
@login_requerido
def verificar_notificaciones():
    u     = usuario_actual()
    ahora = ahora_argentina()
    hoy   = ahora.date()
    notificaciones = []

    # Seguimientos de hoy (solo notificar una vez al día a las 8am)
    hora = ahora.hour
    minuto = ahora.minute
    if hora == 8 and minuto < 2:
        tareas_hoy = Tarea.query.filter(
            Tarea.usuario_id == u.id,
            Tarea.fecha_programada == hoy,
            Tarea.estado == 'pendiente'
        ).all()
        if tareas_hoy:
            notificaciones.append({
                'title': '📋 Seguimientos de hoy',
                'body': f'Tenés {len(tareas_hoy)} seguimiento{"s" if len(tareas_hoy) > 1 else ""} para hoy',
                'tag': f'seguimientos-{hoy}',
                'url': '/'
            })

        # Lunes: reporte propietarios
        if ahora.weekday() == 0:
            props = Propietario.query.filter_by(usuario_id=u.id).count()
            if props > 0:
                notificaciones.append({
                    'title': '🏘️ Reporte semanal',
                    'body': f'Recordá enviar el reporte semanal a tus {props} propietario{"s" if props > 1 else ""}',
                    'tag': f'reporte-{hoy}',
                    'url': '/'
                })

    # Visitas en menos de 2hs
    dos_horas = ahora + timedelta(hours=2)
    visitas = Visita.query.filter(
        Visita.usuario_id == u.id,
        Visita.realizada == False,
        Visita.fecha_hora >= ahora,
        Visita.fecha_hora <= dos_horas
    ).all()
    for v in visitas:
        mins = int((v.fecha_hora - ahora).total_seconds() / 60)
        notificaciones.append({
            'title': '🏠 Visita próxima',
            'body': f'{v.lead.nombre} en {mins} minutos – {v.propiedad}',
            'tag': f'visita-{v.id}-{mins}',
            'url': f'/leads/{v.lead_id}'
        })

    # Llamadas en menos de 10 minutos
    diez_min = ahora + timedelta(minutes=10)
    llamadas = Llamada.query.filter(
        Llamada.usuario_id == u.id,
        Llamada.estado == 'pendiente',
        Llamada.fecha_hora >= ahora,
        Llamada.fecha_hora <= diez_min
    ).all()
    for ll in llamadas:
        mins = int((ll.fecha_hora - ahora).total_seconds() / 60)
        notificaciones.append({
            'title': '📞 Llamada en breve',
            'body': f'{ll.nombre} en {mins} minutos',
            'tag': f'llamada-{ll.id}-{mins}',
            'url': '/llamadas'
        })

    return jsonify({'notificaciones': notificaciones})
