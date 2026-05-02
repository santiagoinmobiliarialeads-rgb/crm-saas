from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Usuario(db.Model):
    __tablename__ = 'usuarios'

    id              = db.Column(db.Integer, primary_key=True)
    email           = db.Column(db.String(120), unique=True, nullable=False)
    password_hash   = db.Column(db.String(256), nullable=False)
    nombre          = db.Column(db.String(100), nullable=False)
    plan            = db.Column(db.String(20), default='basico')
    periodo_prueba  = db.Column(db.Boolean, default=True)
    prueba_expira   = db.Column(db.DateTime, nullable=True)
    activo          = db.Column(db.Boolean, default=True)
    es_admin        = db.Column(db.Boolean, default=False)
    creado_en       = db.Column(db.DateTime, default=datetime.now)

    leads   = db.relationship('Lead',   backref='usuario', lazy=True, cascade='all, delete-orphan')
    visitas = db.relationship('Visita', backref='usuario', lazy=True, cascade='all, delete-orphan')
    tareas  = db.relationship('Tarea',  backref='usuario', lazy=True, cascade='all, delete-orphan')

    PLANES = {
        'basico':  {'nombre': 'Básico',   'limite': 30,  'precio': 10},
        'pro':     {'nombre': 'Pro',      'limite': 70,  'precio': 30},
        'premium': {'nombre': 'Premium',  'limite': 150, 'precio': 40},
    }

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def limite_leads(self):
        if self.es_admin:
            return 99999
        return self.PLANES.get(self.plan, self.PLANES['basico'])['limite']

    @property
    def plan_nombre(self):
        if self.es_admin:
            return 'Admin'
        return self.PLANES.get(self.plan, self.PLANES['basico'])['nombre']

    @property
    def plan_precio(self):
        return self.PLANES.get(self.plan, self.PLANES['basico'])['precio']

    @property
    def leads_count(self):
        return len(self.leads)

    @property
    def puede_crear_lead(self):
        if self.es_admin:
            return True, ''
        if not self.activo:
            return False, 'Tu cuenta está desactivada.'
        if self.periodo_prueba and self.prueba_expira and datetime.now() > self.prueba_expira:
            return False, 'Tu período de prueba venció. Contactá al administrador para activar tu plan.'
        if self.leads_count >= self.limite_leads:
            return False, f'Alcanzaste el límite de {self.limite_leads} leads de tu plan {self.plan_nombre}.'
        return True, ''

    @property
    def dias_prueba_restantes(self):
        if self.periodo_prueba and self.prueba_expira:
            diff = (self.prueba_expira - datetime.now()).days
            return max(0, diff)
        return 0

    @property
    def prueba_activa(self):
        return self.periodo_prueba and self.prueba_expira and datetime.now() <= self.prueba_expira


class Lead(db.Model):
    __tablename__ = 'leads'

    id              = db.Column(db.Integer, primary_key=True)
    usuario_id      = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    nombre          = db.Column(db.String(120), nullable=False)
    telefono        = db.Column(db.String(30), nullable=False)
    estado          = db.Column(db.String(30), default='nuevo')
    temperatura     = db.Column(db.String(20), default='tibio')
    notas           = db.Column(db.Text, default='')
    ultimo_contacto = db.Column(db.DateTime, default=datetime.now)
    creado_en       = db.Column(db.DateTime, default=datetime.now)

    visitas = db.relationship('Visita', backref='lead', lazy=True, cascade='all, delete-orphan')
    tareas  = db.relationship('Tarea',  backref='lead', lazy=True, cascade='all, delete-orphan')

    @property
    def dias_sin_contacto(self):
        if self.ultimo_contacto:
            return (datetime.now() - self.ultimo_contacto).days
        return 999

    @property
    def tareas_pendientes_count(self):
        return sum(1 for t in self.tareas if t.estado == 'pendiente')

    @property
    def visita_proxima(self):
        ahora = datetime.now()
        proximas = [v for v in self.visitas if not v.realizada and v.fecha_hora >= ahora]
        return min(proximas, key=lambda v: v.fecha_hora) if proximas else None


class Visita(db.Model):
    __tablename__ = 'visitas'

    id          = db.Column(db.Integer, primary_key=True)
    usuario_id  = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    lead_id     = db.Column(db.Integer, db.ForeignKey('leads.id'), nullable=False)
    propiedad   = db.Column(db.String(200), nullable=False)
    fecha_hora  = db.Column(db.DateTime, nullable=False)
    notas       = db.Column(db.Text, default='')
    resultado   = db.Column(db.Text, default='')
    realizada   = db.Column(db.Boolean, default=False)
    creado_en   = db.Column(db.DateTime, default=datetime.now)

    tareas = db.relationship('Tarea', backref='visita', lazy=True)

    @property
    def estado_label(self):
        if self.realizada:
            return 'Realizada'
        ahora = datetime.now()
        if self.fecha_hora < ahora:
            return 'Pendiente confirmar'
        diff = self.fecha_hora - ahora
        dias = diff.days
        if dias == 0:
            return f'Hoy a las {self.fecha_hora.strftime("%H:%M")}'
        elif dias == 1:
            return f'Mañana a las {self.fecha_hora.strftime("%H:%M")}'
        else:
            return f'En {dias} días – {self.fecha_hora.strftime("%d/%m a las %H:%M")}'

    @property
    def urgencia(self):
        if self.realizada:
            return 'realizada'
        ahora = datetime.now()
        if self.fecha_hora < ahora:
            return 'vencida'
        diff = (self.fecha_hora - ahora).days
        if diff == 0:
            return 'hoy'
        elif diff == 1:
            return 'manana'
        return 'proxima'


class Tarea(db.Model):
    __tablename__ = 'tareas'

    id               = db.Column(db.Integer, primary_key=True)
    usuario_id       = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    lead_id          = db.Column(db.Integer, db.ForeignKey('leads.id'), nullable=False)
    visita_id        = db.Column(db.Integer, db.ForeignKey('visitas.id'), nullable=True)
    fecha_programada = db.Column(db.Date, nullable=False)
    tipo             = db.Column(db.String(30), nullable=False)
    mensaje_sugerido = db.Column(db.Text, default='')
    estado           = db.Column(db.String(20), default='pendiente')
    completado_en    = db.Column(db.DateTime, nullable=True)
    creado_en        = db.Column(db.DateTime, default=datetime.now)

    TIPOS = {
        'seguimiento_1':  'Seguimiento 1 (24hs)',
        'micro_contacto': 'Micro contacto (día 3-4)',
        'seguimiento_2':  'Seguimiento 2 (día 5-7)',
        'cierre':         'Cierre (día 10-14)',
    }

    @property
    def tipo_label(self):
        return self.TIPOS.get(self.tipo, self.tipo)


class Plantilla(db.Model):
    __tablename__ = 'plantillas'

    id         = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    tipo       = db.Column(db.String(30), nullable=False)
    nombre     = db.Column(db.String(100), nullable=False)
    texto      = db.Column(db.Text, nullable=False)
    creado_en  = db.Column(db.DateTime, default=datetime.now)

    DEFAULTS = {
        'seguimiento_1':  {'nombre': 'Seguimiento 1 (24hs)',      'texto': 'Hola {nombre}! Fue un gusto mostrarte {propiedad} hoy. Me quede pensando en lo que comentaste, creo que tiene mucho potencial. Alguna pregunta que haya surgido?'},
        'micro_contacto': {'nombre': 'Micro contacto (dia 3-4)',   'texto': 'Hola {nombre}! Te comparto algo sobre la zona de {propiedad}. Viene creciendo en valor y hay mucha demanda. Seguis evaluando la opcion?'},
        'seguimiento_2':  {'nombre': 'Seguimiento 2 (dia 5-7)',    'texto': 'Hola {nombre}! {propiedad} sigue disponible y me parece que se ajusta bien a lo que buscas. Podemos charlar 5 minutos esta semana?'},
        'cierre':         {'nombre': 'Cierre (dia 10-14)',         'texto': 'Hola {nombre}! Han pasado unos dias desde que viste {propiedad}. Llegaste a una decision? Te parece si coordinamos el proximo paso?'},
    }
