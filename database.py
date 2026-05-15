

class SuscripcionPush(db.Model):
    __tablename__ = 'suscripciones_push'

    id                = db.Column(db.Integer, primary_key=True)
    usuario_id        = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    subscription_json = db.Column(db.Text, nullable=False)
    creado_en         = db.Column(db.DateTime, default=datetime.now)
