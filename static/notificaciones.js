// InmoCRM – Notificaciones push
const VAPID_PUBLIC_KEY = document.querySelector('meta[name="vapid-public-key"]')?.content;

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  return new Uint8Array([...rawData].map(c => c.charCodeAt(0)));
}

async function iniciarNotificaciones() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    console.log('Notificaciones no soportadas');
    return;
  }

  try {
    const registration = await navigator.serviceWorker.register('/static/sw.js');
    console.log('Service Worker registrado');

    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      console.log('Permiso denegado');
      return;
    }

    // Suscribir al push
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
    });

    // Enviar suscripción al servidor
    await fetch('/notificaciones/suscribir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subscription)
    });

    console.log('Suscripción a notificaciones completada');
  } catch (error) {
    console.error('Error al iniciar notificaciones:', error);
  }
}

// Verificar recordatorios cada minuto
async function verificarRecordatorios() {
  try {
    const res = await fetch('/notificaciones/verificar');
    const data = await res.json();
    if (data.notificaciones && data.notificaciones.length > 0) {
      data.notificaciones.forEach(n => {
        if (Notification.permission === 'granted') {
          new Notification(n.title, {
            body: n.body,
            icon: '/static/icon.png',
            tag: n.tag
          });
        }
      });
    }
  } catch (e) {
    // silencioso
  }
}

// Arrancar cuando carga la página
document.addEventListener('DOMContentLoaded', () => {
  if (VAPID_PUBLIC_KEY) {
    iniciarNotificaciones();
  }
  // Verificar cada minuto
  setInterval(verificarRecordatorios, 60000);
  // También verificar al cargar
  verificarRecordatorios();
});
