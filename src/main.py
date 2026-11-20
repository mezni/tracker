import csv
import io
import os
import re
from datetime import date, datetime

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///roadmap.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# Enforce SQLite foreign key constraints
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# --- Database Models ---
class Roadmap(db.Model):
    __tablename__ = "roadmaps"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    color_hex = db.Column(db.String(7), default="#3b82f6")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    stages = db.relationship(
        "Stage",
        backref="roadmap",
        cascade="all, delete-orphan",
        order_by="Stage.position",
        lazy=True,
    )
    projects = db.relationship(
        "Project",
        backref="roadmap",
        cascade="all, delete-orphan",
        order_by="Project.created_at.desc()",
        lazy=True,
    )
    notes = db.relationship(
        "Note",
        backref="roadmap",
        cascade="all, delete-orphan",
        order_by="Note.updated_at.desc()",
        lazy=True,
    )

    @property
    def progress(self) -> int:
        total = sum(len(s.topics) for s in self.stages)
        if total == 0:
            return 0
        completed = sum(
            1 for s in self.stages for t in s.topics if t.status == "completed"
        )
        return round((completed / total) * 100)


class Stage(db.Model):
    __tablename__ = "stages"
    id = db.Column(db.Integer, primary_key=True)
    roadmap_id = db.Column(
        db.Integer, db.ForeignKey("roadmaps.id", ondelete="CASCADE"), nullable=False
    )
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    position = db.Column(db.Integer, default=0)

    topics = db.relationship(
        "Topic",
        backref="stage",
        cascade="all, delete-orphan",
        order_by="Topic.position",
        lazy=True,
    )


class Topic(db.Model):
    __tablename__ = "topics"
    id = db.Column(db.Integer, primary_key=True)
    stage_id = db.Column(
        db.Integer, db.ForeignKey("stages.id", ondelete="CASCADE"), nullable=False
    )
    title = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(20), default="not_started")
    priority = db.Column(db.String(20), default="medium")
    due_date = db.Column(db.Date, nullable=True)
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Project(db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    roadmap_id = db.Column(
        db.Integer, db.ForeignKey("roadmaps.id", ondelete="CASCADE"), nullable=False
    )
    stage_id = db.Column(
        db.Integer, db.ForeignKey("stages.id", ondelete="SET NULL"), nullable=True
    )
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="planned")
    tech_stack = db.Column(db.String(255))
    repo_url = db.Column(db.String(255))
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    stage = db.relationship("Stage", lazy=True)


class Note(db.Model):
    __tablename__ = "notes"
    id = db.Column(db.Integer, primary_key=True)
    roadmap_id = db.Column(
        db.Integer, db.ForeignKey("roadmaps.id", ondelete="CASCADE"), nullable=False
    )
    stage_id = db.Column(
        db.Integer, db.ForeignKey("stages.id", ondelete="CASCADE"), nullable=True
    )
    topic_id = db.Column(
        db.Integer, db.ForeignKey("topics.id", ondelete="CASCADE"), nullable=True
    )
    title = db.Column(db.String(150), nullable=False)
    content = db.Column(db.Text, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    stage = db.relationship("Stage", lazy=True)
    topic = db.relationship("Topic", lazy=True)


# --- Helpers ---
def parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return None


with app.app_context():
    db.create_all()


# --- Routes ---
@app.route("/")
def index():
    roadmaps = Roadmap.query.order_by(Roadmap.created_at.asc()).all()
    selected_roadmap_id = request.args.get("roadmap_id", type=int)
    selected_roadmap = (
        db.session.get(Roadmap, selected_roadmap_id)
        if selected_roadmap_id
        else (roadmaps[0] if roadmaps else None)
    )
    return render_template(
        "index.html", roadmaps=roadmaps, selected_roadmap=selected_roadmap
    )


# --- Roadmap Routes ---
@app.route("/roadmap/create", methods=["POST"])
def create_roadmap():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    color = request.form.get("color_hex", "#3b82f6")
    if title:
        roadmap = Roadmap(title=title, description=description, color_hex=color)
        db.session.add(roadmap)
        db.session.commit()
        return redirect(url_for("index", roadmap_id=roadmap.id))
    return redirect(url_for("index"))


@app.route("/roadmap/<int:roadmap_id>/edit", methods=["POST"])
def edit_roadmap(roadmap_id: int):
    roadmap = db.get_or_404(Roadmap, roadmap_id)
    title = request.form.get("title", "").strip()
    if title:
        roadmap.title = title
        roadmap.description = request.form.get("description", "").strip()
        roadmap.color_hex = request.form.get("color_hex", roadmap.color_hex)
        db.session.commit()
    return redirect(url_for("index", roadmap_id=roadmap.id))


@app.route("/roadmap/<int:roadmap_id>/delete", methods=["POST"])
def delete_roadmap(roadmap_id: int):
    roadmap = db.get_or_404(Roadmap, roadmap_id)
    db.session.delete(roadmap)
    db.session.commit()
    return redirect(url_for("index"))


# --- Stage Routes ---
@app.route("/roadmap/<int:roadmap_id>/stage/create", methods=["POST"])
def create_stage(roadmap_id: int):
    roadmap = db.get_or_404(Roadmap, roadmap_id)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    if title:
        stage = Stage(
            roadmap_id=roadmap.id,
            title=title,
            description=description,
            position=len(roadmap.stages),
        )
        db.session.add(stage)
        db.session.commit()
    return redirect(url_for("index", roadmap_id=roadmap.id))


@app.route("/stage/<int:stage_id>/edit", methods=["POST"])
def edit_stage(stage_id: int):
    stage = db.get_or_404(Stage, stage_id)
    title = request.form.get("title", "").strip()
    if title:
        stage.title = title
        stage.description = request.form.get("description", "").strip()
        db.session.commit()
    return redirect(url_for("index", roadmap_id=stage.roadmap_id))


@app.route("/stage/<int:stage_id>/delete", methods=["POST"])
def delete_stage(stage_id: int):
    stage = db.get_or_404(Stage, stage_id)
    roadmap_id = stage.roadmap_id
    db.session.delete(stage)
    db.session.commit()
    return redirect(url_for("index", roadmap_id=roadmap_id))


# --- Topic Routes ---
@app.route("/stage/<int:stage_id>/topic/create", methods=["POST"])
def create_topic(stage_id: int):
    stage = db.get_or_404(Stage, stage_id)
    title = request.form.get("title", "").strip()
    priority = request.form.get("priority", "medium")
    due_date = parse_date(request.form.get("due_date"))
    if title:
        topic = Topic(
            stage_id=stage.id,
            title=title,
            priority=priority,
            due_date=due_date,
            position=len(stage.topics),
        )
        db.session.add(topic)
        db.session.commit()
    return redirect(url_for("index", roadmap_id=stage.roadmap_id))


@app.route("/topic/<int:topic_id>/edit", methods=["POST"])
def edit_topic(topic_id: int):
    topic = db.get_or_404(Topic, topic_id)
    title = request.form.get("title", "").strip()
    if title:
        topic.title = title
        topic.status = request.form.get("status", topic.status)
        topic.priority = request.form.get("priority", topic.priority)
        topic.due_date = parse_date(request.form.get("due_date"))
        db.session.commit()
    return redirect(url_for("index", roadmap_id=topic.stage.roadmap_id))


@app.route("/topic/<int:topic_id>/cycle-status", methods=["POST"])
def cycle_topic_status(topic_id: int):
    topic = db.get_or_404(Topic, topic_id)
    cycle = {
        "not_started": "in_progress",
        "in_progress": "completed",
        "completed": "not_started",
    }
    topic.status = cycle.get(topic.status, "not_started")
    db.session.commit()
    return redirect(url_for("index", roadmap_id=topic.stage.roadmap_id))


@app.route("/topic/<int:topic_id>/delete", methods=["POST"])
def delete_topic(topic_id: int):
    topic = db.get_or_404(Topic, topic_id)
    roadmap_id = topic.stage.roadmap_id
    db.session.delete(topic)
    db.session.commit()
    return redirect(url_for("index", roadmap_id=roadmap_id))


# --- Project Routes ---
@app.route("/roadmap/<int:roadmap_id>/project/create", methods=["POST"])
def create_project(roadmap_id: int):
    roadmap = db.get_or_404(Roadmap, roadmap_id)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    stage_id = request.form.get("stage_id", type=int)
    status = request.form.get("status", "planned")
    tech_stack = request.form.get("tech_stack", "").strip()
    repo_url = request.form.get("repo_url", "").strip()
    due_date = parse_date(request.form.get("due_date"))

    if title:
        project = Project(
            roadmap_id=roadmap.id,
            stage_id=stage_id if stage_id else None,
            title=title,
            description=description,
            status=status,
            tech_stack=tech_stack,
            repo_url=repo_url,
            due_date=due_date,
        )
        db.session.add(project)
        db.session.commit()
    return redirect(url_for("index", roadmap_id=roadmap.id))


@app.route("/project/<int:project_id>/edit", methods=["POST"])
def edit_project(project_id: int):
    project = db.get_or_404(Project, project_id)
    title = request.form.get("title", "").strip()
    if title:
        stage_id = request.form.get("stage_id", type=int)
        project.title = title
        project.description = request.form.get("description", "").strip()
        project.stage_id = (
            stage_id if stage_id and db.session.get(Stage, stage_id) else None
        )
        project.status = request.form.get("status", project.status)
        project.tech_stack = request.form.get("tech_stack", "").strip()
        project.repo_url = request.form.get("repo_url", "").strip()
        project.due_date = parse_date(request.form.get("due_date"))
        db.session.commit()
    return redirect(url_for("index", roadmap_id=project.roadmap_id))


@app.route("/project/<int:project_id>/cycle-status", methods=["POST"])
def cycle_project_status(project_id: int):
    project = db.get_or_404(Project, project_id)
    cycle = {
        "planned": "in_progress",
        "in_progress": "completed",
        "completed": "planned",
    }
    project.status = cycle.get(project.status, "planned")
    db.session.commit()
    return redirect(url_for("index", roadmap_id=project.roadmap_id))


@app.route("/project/<int:project_id>/delete", methods=["POST"])
def delete_project(project_id: int):
    project = db.get_or_404(Project, project_id)
    roadmap_id = project.roadmap_id
    db.session.delete(project)
    db.session.commit()
    return redirect(url_for("index", roadmap_id=roadmap_id))


# --- Note Routes ---
@app.route("/roadmap/<int:roadmap_id>/note/create", methods=["POST"])
def create_note(roadmap_id: int):
    roadmap = db.get_or_404(Roadmap, roadmap_id)
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    stage_id = request.form.get("stage_id", type=int)
    topic_id = request.form.get("topic_id", type=int)

    if title and content:
        note = Note(
            roadmap_id=roadmap.id,
            stage_id=stage_id if stage_id else None,
            topic_id=topic_id if topic_id else None,
            title=title,
            content=content,
        )
        db.session.add(note)
        db.session.commit()
    return redirect(url_for("index", roadmap_id=roadmap.id))


@app.route("/note/<int:note_id>/edit", methods=["POST"])
def edit_note(note_id: int):
    note = db.get_or_404(Note, note_id)
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    if title and content:
        stage_id = request.form.get("stage_id", type=int)
        topic_id = request.form.get("topic_id", type=int)
        note.title = title
        note.content = content
        note.stage_id = (
            stage_id if stage_id and db.session.get(Stage, stage_id) else None
        )
        note.topic_id = (
            topic_id if topic_id and db.session.get(Topic, topic_id) else None
        )
        db.session.commit()
    return redirect(url_for("index", roadmap_id=note.roadmap_id))


@app.route("/note/<int:note_id>/delete", methods=["POST"])
def delete_note(note_id: int):
    note = db.get_or_404(Note, note_id)
    roadmap_id = note.roadmap_id
    db.session.delete(note)
    db.session.commit()
    return redirect(url_for("index", roadmap_id=roadmap_id))


# --- Calendar Routes ---
@app.route("/calendar")
def calendar_view():
    return render_template("calendar.html")


@app.route("/api/calendar/events")
def calendar_events_api():
    topics = Topic.query.filter(Topic.due_date.isnot(None)).all()
    projects = Project.query.filter(Project.due_date.isnot(None)).all()

    events = []
    for t in topics:
        events.append(
            {
                "id": f"topic-{t.id}",
                "type": "Topic",
                "title": t.title,
                "date": t.due_date.isoformat(),
                "status": t.status,
                "priority": t.priority,
                "roadmap": t.stage.roadmap.title,
                "roadmap_id": t.stage.roadmap_id,
                "color": t.stage.roadmap.color_hex,
            }
        )
    for p in projects:
        events.append(
            {
                "id": f"project-{p.id}",
                "type": "Project",
                "title": p.title,
                "date": p.due_date.isoformat(),
                "status": p.status,
                "priority": "high",
                "roadmap": p.roadmap.title,
                "roadmap_id": p.roadmap_id,
                "color": p.roadmap.color_hex,
            }
        )
    return jsonify(events)


# --- CSV Backup & Import ---
CSV_COLUMNS = [
    "id",
    "type",
    "parent_id",
    "stage_id",
    "topic_id",
    "title",
    "description",
    "color_hex",
    "status",
    "priority",
    "due_date",
    "position",
    "tech_stack",
    "repo_url",
    "content",
]
CSV_TYPES = {"roadmap", "stage", "topic", "project", "note"}
TOPIC_STATUSES = {"not_started", "in_progress", "completed"}
PROJECT_STATUSES = {"planned", "in_progress", "completed"}
PRIORITIES = {"low", "medium", "high"}
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


def _csv_date(value: date | None) -> str:
    return value.isoformat() if value else ""


def _normalize_csv_row(row: dict) -> dict:
    return {
        column: value.strip() if isinstance(value := row.get(column), str) else ""
        for column in CSV_COLUMNS
    }


def _parse_csv_rows(reader) -> dict:
    rows = {}
    for row in reader:
        line_no = reader.line_num
        data = _normalize_csv_row(row)
        type_ = data["type"].lower()
        key = data["id"]

        if type_ not in CSV_TYPES:
            raise ValueError(f"Line {line_no}: unknown row type '{type_}'.")
        if not key:
            raise ValueError(f"Line {line_no}: id is required.")
        if key in rows:
            raise ValueError(f"Line {line_no}: duplicate id '{key}'.")
        if not data["title"]:
            raise ValueError(f"Line {line_no}: title is required.")

        if type_ == "roadmap":
            data["color_hex"] = data["color_hex"] or "#3b82f6"
            if not COLOR_PATTERN.fullmatch(data["color_hex"]):
                raise ValueError(f"Line {line_no}: color_hex must be #RRGGBB.")
        elif type_ == "topic":
            data["status"] = data["status"] or "not_started"
            data["priority"] = data["priority"] or "medium"
            if data["status"] not in TOPIC_STATUSES:
                raise ValueError(f"Line {line_no}: invalid topic status.")
            if data["priority"] not in PRIORITIES:
                raise ValueError(f"Line {line_no}: invalid topic priority.")
        elif type_ == "project":
            data["status"] = data["status"] or "planned"
            if data["status"] not in PROJECT_STATUSES:
                raise ValueError(f"Line {line_no}: invalid project status.")

        if data["due_date"]:
            try:
                date.fromisoformat(data["due_date"])
            except ValueError as exc:
                raise ValueError(
                    f"Line {line_no}: due_date must be YYYY-MM-DD."
                ) from exc
        if data["position"]:
            try:
                int(data["position"])
            except ValueError as exc:
                raise ValueError(
                    f"Line {line_no}: position must be an integer."
                ) from exc

        rows[key] = (type_, data, line_no)

    def check_reference(key, expected_type, label, line_no, required=True):
        if not key:
            if required:
                raise ValueError(f"Line {line_no}: {label} is required.")
            return
        if key not in rows or rows[key][0] != expected_type:
            raise ValueError(
                f"Line {line_no}: {label} id '{key}' must reference a "
                f"{expected_type} row."
            )

    for type_, data, line_no in rows.values():
        if type_ in {"stage", "project", "note"}:
            check_reference(data["parent_id"], "roadmap", "parent_id", line_no)
        elif type_ == "topic":
            check_reference(data["parent_id"], "stage", "parent_id", line_no)
        if type_ in {"project", "note"} and data["stage_id"]:
            check_reference(data["stage_id"], "stage", "stage_id", line_no, False)
        if type_ == "note" and data["topic_id"]:
            check_reference(data["topic_id"], "topic", "topic_id", line_no, False)

    return rows


@app.route("/api/export/csv")
def export_csv():
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    next_id = 1
    stage_keys = {}
    topic_keys = {}

    def add_row(type_, **fields):
        nonlocal next_id
        row = dict.fromkeys(CSV_COLUMNS, "")
        row["id"] = next_id
        row["type"] = type_
        row.update(fields)
        writer.writerow(row)
        next_id += 1
        return row["id"]

    for roadmap in Roadmap.query.order_by(Roadmap.id).all():
        roadmap_key = add_row(
            "roadmap",
            title=roadmap.title,
            description=roadmap.description or "",
            color_hex=roadmap.color_hex or "#3b82f6",
        )
        for stage in roadmap.stages:
            stage_key = add_row(
                "stage",
                parent_id=roadmap_key,
                title=stage.title,
                description=stage.description or "",
                position=stage.position or 0,
            )
            stage_keys[stage.id] = stage_key
            for topic in stage.topics:
                topic_keys[topic.id] = add_row(
                    "topic",
                    parent_id=stage_key,
                    title=topic.title,
                    status=topic.status or "not_started",
                    priority=topic.priority or "medium",
                    due_date=_csv_date(topic.due_date),
                    position=topic.position or 0,
                )
        for project in roadmap.projects:
            add_row(
                "project",
                parent_id=roadmap_key,
                stage_id=stage_keys.get(project.stage_id, ""),
                title=project.title,
                description=project.description or "",
                status=project.status or "planned",
                tech_stack=project.tech_stack or "",
                repo_url=project.repo_url or "",
                due_date=_csv_date(project.due_date),
            )
        for note in roadmap.notes:
            add_row(
                "note",
                parent_id=roadmap_key,
                stage_id=stage_keys.get(note.stage_id, ""),
                topic_id=topic_keys.get(note.topic_id, ""),
                title=note.title,
                content=note.content,
            )

    return Response(
        output.getvalue().encode("utf-8-sig"),
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=roadmap_backup.csv"},
    )


@app.route("/roadmap/import/csv", methods=["POST"])
def import_csv():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choose a CSV file to import.", "danger")
        return redirect(url_for("index"))

    try:
        reader = csv.DictReader(
            io.StringIO(file.read().decode("utf-8-sig"), newline="")
        )
        if not reader.fieldnames or not {"id", "type", "title"}.issubset(
            reader.fieldnames
        ):
            raise ValueError("CSV must have id, type, and title columns.")
        rows = _parse_csv_rows(reader)
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        flash(f"CSV import failed: {exc}", "danger")
        return redirect(url_for("index"))

    try:
        if request.form.get("replace") == "1":
            db.session.query(Note).delete()
            db.session.query(Project).delete()
            db.session.query(Topic).delete()
            db.session.query(Stage).delete()
            db.session.query(Roadmap).delete()
            db.session.flush()

        created = {}
        for type_ in ("roadmap", "stage", "topic", "project", "note"):
            for key, (row_type, data, _) in rows.items():
                if row_type != type_:
                    continue
                if type_ == "roadmap":
                    obj = Roadmap(
                        title=data["title"],
                        description=data["description"] or None,
                        color_hex=data["color_hex"],
                    )
                elif type_ == "stage":
                    obj = Stage(
                        roadmap_id=created[data["parent_id"]].id,
                        title=data["title"],
                        description=data["description"] or None,
                        position=int(data["position"] or 0),
                    )
                elif type_ == "topic":
                    obj = Topic(
                        stage_id=created[data["parent_id"]].id,
                        title=data["title"],
                        status=data["status"],
                        priority=data["priority"],
                        due_date=date.fromisoformat(data["due_date"])
                        if data["due_date"]
                        else None,
                        position=int(data["position"] or 0),
                    )
                elif type_ == "project":
                    obj = Project(
                        roadmap_id=created[data["parent_id"]].id,
                        stage_id=created[data["stage_id"]].id
                        if data["stage_id"]
                        else None,
                        title=data["title"],
                        description=data["description"] or None,
                        status=data["status"],
                        tech_stack=data["tech_stack"] or None,
                        repo_url=data["repo_url"] or None,
                        due_date=date.fromisoformat(data["due_date"])
                        if data["due_date"]
                        else None,
                    )
                else:
                    obj = Note(
                        roadmap_id=created[data["parent_id"]].id,
                        stage_id=created[data["stage_id"]].id
                        if data["stage_id"]
                        else None,
                        topic_id=created[data["topic_id"]].id
                        if data["topic_id"]
                        else None,
                        title=data["title"],
                        content=data["content"],
                    )
                db.session.add(obj)
                db.session.flush()
                created[key] = obj

        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        app.logger.exception("CSV import failed")
        flash(f"CSV import failed: {exc}", "danger")
        return redirect(url_for("index"))

    counts = dict.fromkeys(CSV_TYPES, 0)
    for type_, _, _ in rows.values():
        counts[type_] += 1
    flash(
        "Imported {roadmap} roadmap(s), {stage} stage(s), {topic} topic(s), "
        "{project} project(s), and {note} note(s).".format(**counts),
        "success",
    )
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
