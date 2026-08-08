/** Leaflet choropleth / marker map for country breakdown widgets. */

export function renderMapWidget(container, payload) {
    container.innerHTML = '';
    const points = payload.map_payload?.points || [];
    if (!points.length) {
        container.textContent = 'No map data';
        return;
    }
    const wrap = document.createElement('div');
    wrap.className = 'report-map-host';
    wrap.style.height = '320px';
    container.appendChild(wrap);

    if (!window.L) {
        const list = document.createElement('ul');
        list.className = 'report-map-fallback';
        points.slice(0, 12).forEach(function (point) {
            const li = document.createElement('li');
            li.textContent = (point.country || point.label || 'Country') + ': ' + (point.value ?? '—');
            list.appendChild(li);
        });
        wrap.appendChild(list);
        return;
    }

    const map = window.L.map(wrap, { scrollWheelZoom: false }).setView([20, 0], 2);
    window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap'
    }).addTo(map);
    points.forEach(function (point) {
        if (point.lat == null || point.lng == null) return;
        window.L.circleMarker([point.lat, point.lng], { radius: 6 }).addTo(map)
            .bindPopup((point.country || '') + ': ' + (point.value ?? '—'));
    });
}
