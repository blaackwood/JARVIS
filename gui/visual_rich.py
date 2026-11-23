"""Safe QPainter renderers for rich teaching-board elements."""
from __future__ import annotations

import math
from functools import lru_cache
from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainterPath, QPen, QPixmap, QPolygonF


def _txt(painter, rect, text, size=10, color=None, align=None, bold=False):
    painter.setPen(color or QColor(225, 239, 249))
    painter.setFont(QFont("Segoe UI", size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
    flags = align if align is not None else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    painter.drawText(rect, flags, str(text))


def _wire_model(painter, center, size, shape, phase, color, view_rotation=(0.0, 0.0)):
    yaw, pitch = view_rotation
    ca, sa = math.cos(phase + yaw), math.sin(phase + yaw)
    cb, sb = math.cos(phase * 0.67 + pitch), math.sin(phase * 0.67 + pitch)

    def project(x, y, z):
        xr = x * ca + z * sa
        zr = -x * sa + z * ca
        yr = y * cb - zr * sb
        return QPointF(center.x() + xr * size, center.y() + yr * size)

    painter.save()
    pen = QPen(color, 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if shape == "cube":
        verts = [project(x, y, z) for x, y, z in (
            (-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
            (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
        edges = ((0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),
                 (0,4),(1,5),(2,6),(3,7))
        for a, b in edges:
            painter.drawLine(verts[a], verts[b])
    elif shape == "sphere":
        for latitude in (-0.78, -0.42, 0, 0.42, 0.78):
            path = QPainterPath()
            for i in range(65):
                t = math.tau * i / 64
                v = project(math.cos(latitude)*math.cos(t),
                            math.sin(latitude),
                            math.cos(latitude)*math.sin(t))
                if i == 0: path.moveTo(v)
                else: path.lineTo(v)
            painter.drawPath(path)
        for longitude in range(0, 180, 30):
            path = QPainterPath()
            a = math.radians(longitude)
            for i in range(65):
                t = math.tau * i / 64
                v = project(math.cos(t)*math.cos(a), math.sin(t),
                            math.cos(t)*math.sin(a))
                if i == 0: path.moveTo(v)
                else: path.lineTo(v)
            painter.drawPath(path)
    elif shape in {"cylinder", "cone"}:
        for y in (-1, 1):
            if shape == "cone" and y == 1:
                continue
            path = QPainterPath()
            for i in range(65):
                t = math.tau * i / 64
                v = project(math.cos(t), y, math.sin(t))
                if i == 0: path.moveTo(v)
                else: path.lineTo(v)
            painter.drawPath(path)
        if shape == "cone":
            tip = project(0, -1, 0)
            for i in range(0, 360, 30):
                t = math.radians(i)
                painter.drawLine(tip, project(math.cos(t), 1, math.sin(t)))
        else:
            for i in range(0, 360, 45):
                t = math.radians(i)
                painter.drawLine(project(math.cos(t), -1, math.sin(t)),
                                 project(math.cos(t), 1, math.sin(t)))
    else:  # torus represented by rotating elliptical rings
        for ring in range(5):
            radius = 0.48 + ring * 0.12
            path = QPainterPath()
            for i in range(65):
                t = math.tau * i / 64
                v = project(math.cos(t)*radius, math.sin(t)*0.38,
                            math.sin(t)*radius*0.55)
                if i == 0: path.moveTo(v)
                else: path.lineTo(v)
            painter.drawPath(path)
    painter.restore()



def _unit_normal(a, b, c):
    ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    length = max(1e-9, math.sqrt(nx*nx+ny*ny+nz*nz))
    return (nx/length, ny/length, nz/length)


@lru_cache(maxsize=5)
def _solid_mesh(shape):
    """Return a small cached triangle mesh with outward-facing surface normals."""
    triangles = []

    def add(a, b, c, normal=None):
        n = normal or _unit_normal(a, b, c)
        triangles.append((a, b, c, n))

    if shape == "cube":
        faces = [
            ((1,0,0),  [(0.5,-0.5,-0.5),(0.5,0.5,-0.5),(0.5,0.5,0.5),(0.5,-0.5,0.5)]),
            ((-1,0,0), [(-0.5,-0.5,0.5),(-0.5,0.5,0.5),(-0.5,0.5,-0.5),(-0.5,-0.5,-0.5)]),
            ((0,1,0),  [(-0.5,0.5,-0.5),(-0.5,0.5,0.5),(0.5,0.5,0.5),(0.5,0.5,-0.5)]),
            ((0,-1,0), [(0.5,-0.5,-0.5),(0.5,-0.5,0.5),(-0.5,-0.5,0.5),(-0.5,-0.5,-0.5)]),
            ((0,0,1),  [(-0.5,-0.5,0.5),(0.5,-0.5,0.5),(0.5,0.5,0.5),(-0.5,0.5,0.5)]),
            ((0,0,-1), [(-0.5,0.5,-0.5),(0.5,0.5,-0.5),(0.5,-0.5,-0.5),(-0.5,-0.5,-0.5)]),
        ]
        for normal, q in faces:
            add(q[0], q[1], q[2], normal)
            add(q[0], q[2], q[3], normal)

    elif shape == "sphere":
        nu, nv = 20, 12
        def point(u, v):
            t, f = u*math.tau, v*math.pi
            n = (math.sin(f)*math.cos(t), math.cos(f), math.sin(f)*math.sin(t))
            return tuple(0.5*x for x in n), n
        for i in range(nu):
            for j in range(nv):
                p00,n00=point(i/nu,j/nv); p10,n10=point((i+1)/nu,j/nv)
                p11,n11=point((i+1)/nu,(j+1)/nv); p01,n01=point(i/nu,(j+1)/nv)
                add(p00,p10,p11,_avg_normal(n00,n10,n11))
                add(p00,p11,p01,_avg_normal(n00,n11,n01))

    elif shape in {"cylinder", "cone"}:
        nu = 24
        top_radius = 0.0 if shape == "cone" else 0.5
        bottom_radius = 0.5
        for i in range(nu):
            t0,t1=math.tau*i/nu,math.tau*(i+1)/nu
            b0=(math.cos(t0)*bottom_radius,-0.5,math.sin(t0)*bottom_radius)
            b1=(math.cos(t1)*bottom_radius,-0.5,math.sin(t1)*bottom_radius)
            if top_radius > 0:
                t0p=(math.cos(t0)*top_radius,0.5,math.sin(t0)*top_radius)
                t1p=(math.cos(t1)*top_radius,0.5,math.sin(t1)*top_radius)
                n0=(math.cos(t0),0.0,math.sin(t0))
                n1=(math.cos(t1),0.0,math.sin(t1))
                add(b0,b1,t1p,_avg_normal(n0,n1,n1))
                add(b0,t1p,t0p,_avg_normal(n0,n1,n0))
                add((0,-0.5,0),b1,b0,(0,-1,0))
                add((0,0.5,0),t0p,t1p,(0,1,0))
            else:
                tip=(0,0.5,0)
                n0=(math.cos(t0),0.5,math.sin(t0))
                n1=(math.cos(t1),0.5,math.sin(t1))
                add(b0,b1,tip,_avg_normal(n0,n1,(0.0,0.5,0.0)))
                add((0,-0.5,0),b1,b0,(0,-1,0))

    elif shape == "torus":
        nu,nv=24,10
        major,minor=0.36,0.14
        def point(u,v):
            t,f=u*math.tau,v*math.tau
            c=(math.cos(t),0,math.sin(t))
            n=(math.cos(f)*c[0],math.sin(f),math.cos(f)*c[2])
            pos=(c[0]*major+n[0]*minor,n[1]*minor,c[2]*major+n[2]*minor)
            return pos,n
        for i in range(nu):
            for j in range(nv):
                p00,n00=point(i/nu,j/nv); p10,n10=point((i+1)/nu,j/nv)
                p11,n11=point((i+1)/nu,(j+1)/nv); p01,n01=point(i/nu,(j+1)/nv)
                add(p00,p10,p11,_avg_normal(n00,n10,n11))
                add(p00,p11,p01,_avg_normal(n00,n11,n01))
    return tuple(triangles)


def _avg_normal(*normals):
    x=sum(n[0] for n in normals)
    y=sum(n[1] for n in normals)
    z=sum(n[2] for n in normals)
    length=max(1e-9,math.sqrt(x*x+y*y+z*z))
    return (x/length,y/length,z/length)


def _solid_model(painter, center, size, shape, phase, color, view_rotation=(0.0, 0.0)):
    """CPU shaded 3D mesh: perspective, depth sorting, Lambert light and rim highlight."""
    triangles = _solid_mesh(shape if shape in {"cube","sphere","cylinder","cone","torus"} else "cube")
    size *= 2.0  # mesh primitives are normalised to a 0.5 radius, unlike the legacy wireframe.
    yaw,pitch=view_rotation
    ca,sa=math.cos(phase+yaw),math.sin(phase+yaw)
    cb,sb=math.cos(phase*0.67+pitch),math.sin(phase*0.67+pitch)
    light=(-0.42,0.76,0.50)
    ll=math.sqrt(sum(v*v for v in light))
    light=tuple(v/ll for v in light)

    def rotate(v):
        x,y,z=v
        xr=x*ca+z*sa
        zr=-x*sa+z*ca
        yr=y*cb-zr*sb
        z2=y*sb+zr*cb
        return (xr,yr,z2)

    def screen(v):
        xr,yr,zr=v
        factor=3.5/max(1.8,3.5-zr)
        return QPointF(center.x()+xr*size*factor,
                       center.y()-yr*size*factor)

    faces=[]
    for a,b,c,n in triangles:
        nr=rotate(n)
        # Back-face culling: the desktop painter needs only visible front surfaces.
        if nr[2] <= 0.015:
            continue
        verts=(rotate(a),rotate(b),rotate(c))
        depth=(verts[0][2]+verts[1][2]+verts[2][2])/3
        pts=[screen(v) for v in verts]
        diffuse=max(0.0,nr[0]*light[0]+nr[1]*light[1]+nr[2]*light[2])
        rim=(1.0-max(0.0,min(1.0,nr[2])))**2
        intensity=max(0.18,min(1.12,0.25+0.66*diffuse+0.24*rim))
        fill=QColor(
            max(0,min(255,int(color.red()*intensity))),
            max(0,min(255,int(color.green()*intensity))),
            max(0,min(255,int(color.blue()*intensity))),
            248,
        )
        faces.append((depth,pts,fill))
    # Far triangles first; nearer triangles naturally paint over them.
    faces.sort(key=lambda item:item[0])
    painter.save()
    painter.setPen(QPen(QColor(color.red(),color.green(),color.blue(),52),0.48))
    for _,pts,fill in faces:
        painter.setBrush(fill)
        painter.drawPolygon(QPolygonF(pts))
    # A restrained highlight along the upper/front rim makes the surface read as glassy metal.
    painter.setPen(QPen(QColor(235,250,255,80),0.8))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if shape == "cube":
        arc=QPainterPath()
        arc.moveTo(screen(rotate((-0.5,0.5,0.5))))
        arc.lineTo(screen(rotate((0.5,0.5,0.5))))
        arc.lineTo(screen(rotate((0.5,0.5,-0.5))))
        painter.drawPath(arc)
    painter.restore()



_ELEMENT_TONES = {
    "C": QColor(220, 229, 238), "H": QColor(245, 248, 252),
    "O": QColor(255, 105, 112), "N": QColor(94, 151, 255),
    "S": QColor(255, 204, 74), "P": QColor(255, 153, 69),
    "F": QColor(121, 230, 146), "Cl": QColor(121, 230, 146),
    "Br": QColor(189, 112, 86), "I": QColor(177, 132, 220),
    "Na": QColor(174, 118, 235), "Fe": QColor(211, 116, 83),
    "Ca": QColor(148, 211, 226), "Mg": QColor(119, 205, 161),
}


def _draw_photo(painter, box, item, color):
    """Draw an already-vetted local image payload. No network access in the renderer."""
    x, y, w, h = box.x(), box.y(), box.width(), box.height()
    data = item.get("photo_data") or b""
    pixmap = QPixmap()
    if data:
        try:
            pixmap.loadFromData(data)
        except Exception:
            pass
    photo_rect = QRectF(x+12, y+42, w-24, max(30, h-82))
    painter.save()
    painter.setClipRect(photo_rect)
    if not pixmap.isNull():
        scaled = pixmap.scaled(
            QSize(max(1, int(photo_rect.width())), max(1, int(photo_rect.height()))),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        target = QRectF(
            photo_rect.center().x()-scaled.width()/2,
            photo_rect.center().y()-scaled.height()/2,
            scaled.width(), scaled.height(),
        )
        painter.drawPixmap(target, scaled, QRectF(pixmap.rect()))
    else:
        painter.setPen(QPen(QColor(color.red(),color.green(),color.blue(),90),1))
        painter.setBrush(QColor(color.red(),color.green(),color.blue(),24))
        painter.drawRoundedRect(photo_rect,8,8)
        message = item.get("photo_error") or "Imagem indisponível"
        _txt(painter,photo_rect.adjusted(8,5,-8,-5),message,9,
             QColor(194,213,228),Qt.AlignmentFlag.AlignCenter)
    painter.restore()
    caption = item.get("caption") or item.get("photo_title") or ""
    credit = item.get("credit") or ""
    if caption:
        _txt(painter,QRectF(x+12,y+h-36,w-24,20),caption,9,
             QColor(232,243,251),bold=True)
    if credit:
        _txt(painter,QRectF(x+12,y+h-17,w-24,12),credit,7,
             QColor(137,165,185))


def _draw_geo_map(painter, box, item, color):
    """Equirectangular locator map with real lat/lon pins and named route links."""
    x,y,w,h=box.x(),box.y(),box.width(),box.height()
    plot=QRectF(x+18,y+43,w-36,h-62)
    if plot.width()<30 or plot.height()<30:
        return
    painter.save()
    painter.setPen(QPen(QColor(125,165,190,55),0.8))
    for lat in (-60,-30,0,30,60):
        yy=plot.top()+(90-lat)/180*plot.height()
        painter.drawLine(QPointF(plot.left(),yy),QPointF(plot.right(),yy))
    for lon in (-120,-60,0,60,120):
        xx=plot.left()+(lon+180)/360*plot.width()
        painter.drawLine(QPointF(xx,plot.top()),QPointF(xx,plot.bottom()))
    painter.setPen(QPen(QColor(140,175,198,130),1))
    painter.setBrush(QColor(14,35,49,180))
    painter.drawRoundedRect(plot,5,5)
    pins=item.get("pins") or []
    by_name={pin.get("name"):pin for pin in pins if pin.get("name")}
    def project(pin):
        return QPointF(
            plot.left()+(float(pin["lon"])+180)/360*plot.width(),
            plot.top()+(90-float(pin["lat"]))/180*plot.height(),
        )
    for route in item.get("routes") or []:
        a=by_name.get(route.get("from")); b=by_name.get(route.get("to"))
        if not a or not b: continue
        p1,p2=project(a),project(b)
        painter.setPen(QPen(QColor(color.red(),color.green(),color.blue(),205),2,
                            Qt.PenStyle.DashLine,Qt.PenCapStyle.RoundCap))
        mid=QPointF((p1.x()+p2.x())/2,(p1.y()+p2.y())/2-10)
        path=QPainterPath(p1); path.quadTo(mid,p2); painter.drawPath(path)
        if route.get("label"):
            _txt(painter,QRectF(mid.x()-45,mid.y()-18,90,15),route["label"],7,color,
                 Qt.AlignmentFlag.AlignCenter)
    for i,pin in enumerate(pins):
        pt=project(pin)
        painter.setPen(QPen(QColor(6,18,29,235),2))
        painter.setBrush(QColor(255,207,92))
        painter.drawEllipse(pt,6,6)
        painter.setPen(QPen(QColor(255,245,211),1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(pt,3,3)
        label=str(pin.get("name") or "")[:28]
        # Place names to the right, but switch left near the right edge.
        label_x=pt.x()+9
        if label_x+100>plot.right(): label_x=pt.x()-105
        label_y=max(plot.top()+2,min(plot.bottom()-17,pt.y()-16))
        _txt(painter,QRectF(label_x,label_y,100,17),label,8,
             QColor(242,247,251),bold=True)
    _txt(painter,QRectF(plot.left()+5,plot.bottom()-15,plot.width()-10,12),
         "Longitude / latitude",7,QColor(126,157,178))
    painter.restore()


def _draw_molecule(painter, box, item, color):
    """Draw atom/bond structure with element colours and explicit bond order."""
    x,y,w,h=box.x(),box.y(),box.width(),box.height()
    atoms=item.get("atoms") or []
    bonds=item.get("bonds") or []
    if not atoms: return
    area=QRectF(x+16,y+46,w-32,h-78)
    pts=[
        QPointF(area.left()+area.width()*float(a.get("x",50))/100,
                area.top()+area.height()*float(a.get("y",50))/100)
        for a in atoms
    ]
    painter.save()
    # Bonds are painted first, then atoms; double/triple bonds use parallel offsets.
    for bond in bonds:
        try:
            ia,ib=int(bond["a"]),int(bond["b"])
            if not (0<=ia<len(pts) and 0<=ib<len(pts)): continue
            a,b=pts[ia],pts[ib]
            dx,dy=b.x()-a.x(),b.y()-a.y()
            length=max(0.001,math.hypot(dx,dy))
            nx,ny=-dy/length,dx/length
            order=float(bond.get("order",1))
            offsets=(0,) if order<1.7 else ((-3,3) if order<2.7 else (-4,0,4))
            painter.setPen(QPen(QColor(177,205,222,220),2,Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            for off in offsets:
                painter.drawLine(QPointF(a.x()+nx*off,a.y()+ny*off),
                                 QPointF(b.x()+nx*off,b.y()+ny*off))
            if abs(order-1.5)<0.1:
                painter.setPen(QPen(QColor(177,205,222,190),1,Qt.PenStyle.DotLine))
                painter.drawLine(QPointF(a.x()+nx*4,a.y()+ny*4),
                                 QPointF(b.x()+nx*4,b.y()+ny*4))
        except (KeyError,TypeError,ValueError):
            continue
    for atom,pt in zip(atoms,pts):
        symbol=str(atom.get("element") or "?")[:2]
        tone=_ELEMENT_TONES.get(symbol,QColor(180,202,219))
        r=13 if len(symbol)==1 else 16
        painter.setPen(QPen(QColor(7,19,29,230),2))
        painter.setBrush(QColor(15,35,49,245))
        painter.drawEllipse(pt,r,r)
        painter.setPen(QPen(tone,1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(pt,r,r)
        _txt(painter,QRectF(pt.x()-r,pt.y()-r,2*r,2*r),symbol,10,tone,
             Qt.AlignmentFlag.AlignCenter,True)
        charge=int(atom.get("charge",0) or 0)
        if charge:
            mark=("+" if charge>0 else "−")+(str(abs(charge)) if abs(charge)>1 else "")
            _txt(painter,QRectF(pt.x()+r-1,pt.y()-r-5,22,14),mark,7,
                 QColor(255,207,112),bold=True)
    painter.restore()
    _txt(painter,QRectF(x+12,y+h-28,w-24,18),
         f"{len(atoms)} átomos · {len(bonds)} ligações",8,
         QColor(151,181,201),Qt.AlignmentFlag.AlignCenter)


_HOLO_DISABLED = False
_LEGACY_SHAPE = {"capsule": "cylinder", "disc": "cylinder", "pyramid": "cone",
                 "ring": "torus", "plane": "cube", "none": "sphere"}


def _draw_holo_model(painter, box, item, color, phase) -> bool:
    """Render a model3d on the GPU. False => caller uses the software renderer."""
    global _HOLO_DISABLED
    if _HOLO_DISABLED:
        return False
    try:
        from gui.holo3d import get_renderer
        renderer = get_renderer()
        if renderer is None:
            _HOLO_DISABLED = True
            return False
        w, h = int(box.width()), int(box.height())
        view = item.get("_view_rotation") or (0.0, 0.0)
        # The board already reveals each element progressively (clip + fade).
        image, labels = renderer.render([item], w, h, phase, view=view)
        if image is None:
            return False
        painter.drawImage(box, image)
        for lab in labels:
            lx = box.left() + lab["x"] * box.width()
            ly = box.top() + lab["y"] * box.height()
            text = lab["text"]
            tw = 7.2 * len(text) + 16
            pill = QRectF(lx - tw / 2, ly - 11, tw, 20)
            painter.save()
            painter.setPen(QPen(QColor(int(lab["color"][0] * 255), int(lab["color"][1] * 255),
                                       int(lab["color"][2] * 255), 150), 1))
            painter.setBrush(QColor(7, 18, 30, 190))
            painter.drawRoundedRect(pill, 9, 9)
            painter.restore()
            _txt(painter, pill, text, 9, QColor(236, 247, 255), Qt.AlignmentFlag.AlignCenter, True)
        title = item.get("title")
        if title:
            _txt(painter, QRectF(box.left() + 8, box.bottom() - 26, box.width() - 16, 20),
                 title, 10, color, Qt.AlignmentFlag.AlignCenter, True)
        return True
    except Exception:
        import logging
        logging.getLogger(__name__).exception("holo3d render failed; using software 3D")
        _HOLO_DISABLED = True
        return False


def draw_rich_element(painter, canvas, item, color, phase=0.0):
    """Draw one structured board object. Returns clickable quiz hit rectangles."""
    kind = item.get("type")
    x = canvas.left() + canvas.width() * float(item.get("x", 50)) / 100
    y = canvas.top() + canvas.height() * float(item.get("y", 50)) / 100
    w = max(120, canvas.width() * float(item.get("width", 36)) / 100)
    h = max(90, canvas.height() * float(item.get("height", 32)) / 100)
    box = QRectF(x, y, w, h)
    hit_regions = []

    if kind == "model3d":
        if str(item.get("render_style") or "").lower() != "wireframe" or item.get("parts"):
            if _draw_holo_model(painter, box, item, color, phase):
                return hit_regions
        center = QPointF(x + w * 0.5, y + h * 0.52)
        shape = _LEGACY_SHAPE.get(item.get("shape", "cube"), item.get("shape", "cube"))
        render_style = str(item.get("render_style") or "solid").lower()
        renderer = _wire_model if render_style == "wireframe" else _solid_model
        view_rotation = item.get("_view_rotation") or (0.0, 0.0)
        renderer(painter, center, min(w, h) * 0.23, shape,
                 phase * float(item.get("rotation_speed", 0.8)), color, view_rotation)
        for part in item.get("parts", []):
            motion = part.get("motion", "none")
            t = phase * float(part.get("speed", 1))
            dx, dy = float(part.get("dx", 0)), float(part.get("dy", 0))
            if motion == "orbit":
                dx += math.cos(t) * 11
                dy += math.sin(t) * 8
            elif motion == "slide":
                dx += math.sin(t) * 9
            scale = float(part.get("size", 10)) / 20
            if motion == "pulse":
                scale *= 1 + 0.14 * math.sin(t)
            pc = QPointF(center.x() + dx*w/100, center.y() + dy*h/100)
            part_renderer = _wire_model if part.get("render_style") == "wireframe" else renderer
            renderer_view = view_rotation
            part_renderer(painter, pc, min(w, h)*0.23*scale,
                          _LEGACY_SHAPE.get(part.get("shape", "sphere"), part.get("shape", "sphere")),
                          t if motion in {"spin", "orbit"} else 0,
                          color, renderer_view)
            if part.get("label"):
                _txt(painter, QRectF(pc.x()-55, pc.y()+14, 110, 22),
                     part["label"], 8, QColor(232,244,252),
                     Qt.AlignmentFlag.AlignCenter)
        _txt(painter, QRectF(x+8, y+h-28, w-16, 20),
             item.get("title") or shape.title(), 10, color,
             Qt.AlignmentFlag.AlignCenter, True)
        return hit_regions

    painter.save()
    painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 130), 1.2))
    painter.setBrush(QColor(9, 22, 36, 232))
    painter.drawRoundedRect(box, 12, 12)
    heading = item.get("title") or item.get("heading") or item.get("text") or kind.title()
    _txt(painter, QRectF(x+13, y+7, w-26, 30), heading, 12,
         QColor(243,249,255), bold=True)

    body_top = y + 42
    body = QRectF(x+13, body_top, w-26, h-52)
    if kind == "photo":
        _draw_photo(painter,box,item,color)
    elif kind == "map":
        _draw_geo_map(painter,box,item,color)
    elif kind == "molecule":
        _draw_molecule(painter,box,item,color)
    elif kind in {"card", "list"}:
        values = item.get("items") or []
        text = item.get("text", "")
        if text and text != heading:
            _txt(painter, body, text, 10, QColor(193,215,231),
                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        if values:
            row_h = max(20, (body.height()- (34 if text else 0)) / len(values))
            for i, value in enumerate(values):
                _txt(painter, QRectF(body.left(), body.top()+i*row_h, body.width(), row_h),
                     "• " + value, 9, color)

    elif kind == "table":
        columns = item.get("columns") or []
        rows = item.get("rows") or []
        if columns:
            row_h = max(22, body.height() / max(1, len(rows)+1))
            col_w = body.width() / len(columns)
            for ri, row in enumerate([columns] + rows):
                for ci, value in enumerate(row[:len(columns)]):
                    cell = QRectF(body.left()+ci*col_w, body.top()+ri*row_h,
                                  col_w, row_h)
                    painter.setPen(QPen(QColor(color.red(),color.green(),color.blue(),90), .8))
                    painter.setBrush(QColor(color.red(),color.green(),color.blue(),38)
                                     if ri == 0 else QColor(20,38,55,220))
                    painter.drawRect(cell)
                    _txt(painter, cell.adjusted(5,1,-4,-1), value, 8,
                         QColor(244,248,252) if ri == 0 else QColor(196,216,231),
                         bold=(ri == 0))

    elif kind == "timeline":
        events = item.get("events") or []
        base = y + h * .58
        painter.setPen(QPen(color, 2))
        painter.drawLine(QPointF(x+22, base), QPointF(x+w-22, base))
        for i, entry in enumerate(events):
            px = x+22 + (w-44)*i/max(1,len(events)-1)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(px,base),5,5)
            upper = i % 2 == 0
            stem = base + (-24 if upper else 24)
            painter.drawLine(QPointF(px,base), QPointF(px,stem))
            _txt(painter, QRectF(px-52, stem+(-34 if upper else 4), 104, 18),
                 entry.get("when", ""), 8, color, Qt.AlignmentFlag.AlignCenter, True)
            _txt(painter, QRectF(px-56, stem+(-17 if upper else 20), 112, 34),
                 entry.get("text", ""), 8, QColor(203,220,234), Qt.AlignmentFlag.AlignCenter)

    elif kind == "graph":
        plot = QRectF(x+34, y+42, w-48, h-60)
        painter.setPen(QPen(QColor(130,165,190,55), .8))
        for i in range(6):
            gx = plot.left()+plot.width()*i/5
            gy = plot.top()+plot.height()*i/5
            painter.drawLine(QPointF(gx,plot.top()), QPointF(gx,plot.bottom()))
            painter.drawLine(QPointF(plot.left(),gy), QPointF(plot.right(),gy))
        painter.setPen(QPen(QColor(220,235,245),1.2))
        painter.drawLine(plot.bottomLeft(),plot.bottomRight())
        painter.drawLine(plot.bottomLeft(),plot.topLeft())
        for series in item.get("plots") or []:
            points = [QPointF(plot.left()+plot.width()*pt["x"]/100,
                              plot.bottom()-plot.height()*pt["y"]/100)
                      for pt in series.get("points",[])]
            if len(points) >= 2:
                path = QPainterPath(points[0])
                for pt in points[1:]: path.lineTo(pt)
                painter.setPen(QPen(color,2.2))
                painter.drawPath(path)
                painter.setBrush(color)
                for pt in points: painter.drawEllipse(pt,3,3)
        for dot in item.get("dots") or []:
            pt = QPointF(plot.left()+plot.width()*dot["x"]/100,
                         plot.bottom()-plot.height()*dot["y"]/100)
            painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(color)
            painter.drawEllipse(pt,4,4)
            if dot.get("label"):
                _txt(painter, QRectF(pt.x()+5,pt.y()-16,100,20),dot["label"],8)

    elif kind == "mindmap":
        branches = item.get("branches") or []
        center = QPointF(x+w*.5,y+h*.52)
        painter.setPen(QPen(color,2)); painter.setBrush(QColor(color.red(),color.green(),color.blue(),55))
        painter.drawEllipse(center,54,28)
        _txt(painter,QRectF(center.x()-50,center.y()-17,100,34),heading,9,
             QColor(245,250,255),Qt.AlignmentFlag.AlignCenter,True)
        for i, branch in enumerate(branches):
            angle = -math.pi/2 + math.tau*i/max(1,len(branches))
            end = QPointF(center.x()+math.cos(angle)*w*.34,
                          center.y()+math.sin(angle)*h*.34)
            painter.setPen(QPen(color,1.5)); painter.drawLine(center,end)
            node = QRectF(end.x()-54,end.y()-23,108,46)
            painter.setPen(QPen(QColor(color.red(),color.green(),color.blue(),150),1))
            painter.setBrush(QColor(17,37,54,225)); painter.drawRoundedRect(node,8,8)
            _txt(painter,node.adjusted(5,3,-5,-3),branch.get("text",""),8,
                 QColor(241,247,253),Qt.AlignmentFlag.AlignCenter,True)

    elif kind == "quiz":
        options = item.get("options") or []
        row_h = max(26, (body.height()-26) / max(1,len(options)))
        selected = item.get("selected")
        for i, option in enumerate(options):
            option_box = QRectF(body.left(), body.top()+i*row_h,
                                body.width(), row_h-4)
            chosen = selected == i
            painter.setPen(QPen(color if chosen else QColor(120,160,190,100),1))
            painter.setBrush(QColor(color.red(),color.green(),color.blue(),60)
                             if chosen else QColor(25,45,63,220))
            painter.drawRoundedRect(option_box,7,7)
            _txt(painter,option_box.adjusted(8,2,-6,-2),
                 f"{chr(65+i)}. {option}",9,QColor(245,249,255))
            hit_regions.append((item.get("id"),i,option_box))
        if selected is not None and 0 <= int(selected) < len(options):
            expected = str(item.get("answer") or "").strip()
            actual = str(options[int(selected)]).strip()
            letter = expected.upper().strip(" .)")
            if len(letter) == 1 and letter in "ABCD":
                is_correct = (ord(letter) - ord("A")) == int(selected)
            else:
                is_correct = bool(expected) and actual.casefold() == expected.casefold()
            if not expected:
                feedback = "Resposta registrada · JARVIS fará a correção. "
                tone = QColor(255, 204, 132)
            else:
                feedback = ("Correto! " if is_correct else "Não é essa. ")
                tone = QColor(142,240,188) if is_correct else QColor(255,187,127)
            feedback += str(item.get("explanation") or "")
            _txt(painter,QRectF(x+12,y+h-25,w-24,18),feedback[:140],8,tone,bold=True)
    painter.restore()
    return hit_regions
