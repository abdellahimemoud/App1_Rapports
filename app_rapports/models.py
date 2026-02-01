from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max


# =======================
# CONNEXION BASE DE DONNÉES
# =======================
class DatabaseConnection(models.Model):

    DB_TYPES = [
        ('oracle', 'Oracle'),
        ('mysql', 'MySQL'),
        ('postgres', 'PostgreSQL'),
    ]

    name = models.CharField(max_length=200)

    db_type = models.CharField(
        max_length=20,
        choices=DB_TYPES,
        default='oracle'
    )

    host = models.CharField(max_length=200)
    port = models.PositiveIntegerField(default=1521)
    user = models.CharField(max_length=200)

    password = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )

    database_name = models.CharField(
        max_length=200,
        help_text="MySQL/Postgres: DB name | Oracle: SERVICE_NAME (ex: FREEPDB1)"
    )

    def __str__(self):
        return f"{self.name} ({self.db_type})"


# =======================
# REQUÊTE SQL
# =======================
class SqlQuery(models.Model):
    name = models.CharField(max_length=200)

    database = models.ForeignKey(
        DatabaseConnection,
        on_delete=models.CASCADE,
        related_name="queries"
    )

    sql_text = models.TextField(verbose_name="Requête SQL")

    # ✅ TOTAUX (REQUÊTE SEULE)
    enable_totals = models.BooleanField(default=False)
    total_columns = models.JSONField(default=list, blank=True)
    total_label = models.CharField(
        max_length=200,
        default="TOTAL",
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# =======================
# RAPPORT
# =======================
class Report(models.Model):

    PERIODIC_TYPE_CHOICES = [
        ("daily", "Chaque jour"),
        ("weekly", "Chaque semaine"),
        ("monthly", "Chaque mois"),
    ]

    WEEKDAY_CHOICES = [
        ("mon", "Lundi"),
        ("tue", "Mardi"),
        ("wed", "Mercredi"),
        ("thu", "Jeudi"),
        ("fri", "Vendredi"),
        ("sat", "Samedi"),
        ("sun", "Dimanche"),
    ]

    # 🔑 CODE UNIQUE DU RAPPORT
    code = models.CharField(
        max_length=10,
        unique=True,
        blank=True,
        null=True
    )

    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=255)
    message = models.TextField(blank=True, null=True)

    # 🔥 Plusieurs requêtes par rapport
    queries = models.ManyToManyField(
        SqlQuery,
        related_name="reports"
    )

    execute_at = models.DateTimeField(blank=True, null=True)

    is_periodic = models.BooleanField(default=False)
    periodic_type = models.CharField(
        max_length=10,
        choices=PERIODIC_TYPE_CHOICES,
        blank=True,
        null=True
    )
    periodic_time = models.TimeField(blank=True, null=True)
    periodic_weekday = models.CharField(
        max_length=3,
        choices=WEEKDAY_CHOICES,
        blank=True,
        null=True
    )
    periodic_monthday = models.PositiveIntegerField(blank=True, null=True)

    last_executed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # =======================
    # GÉNÉRATION DU CODE
    # =======================
    def save(self, *args, **kwargs):
        if not self.code or self.code.strip() == "":
            self.code = self.generate_code()
        super().save(*args, **kwargs)

    def generate_code(self):
        """
        Génère un code unique du type R-01, R-02, R-03...
        Fonctionne même si des rapports sont supprimés.
        """
        with transaction.atomic():
            last_code = (
                Report.objects
                .filter(code__startswith="R-")
                .aggregate(max_code=Max("code"))
                ["max_code"]
            )

            if not last_code:
                return "R-01"

            last_number = int(last_code.split("-")[1])
            return f"R-{last_number + 1:02d}"

    def clean(self):
        """
        Validation métier :
        - Rapport périodique → type + heure obligatoires
        - Rapport ponctuel → date future obligatoire
        """
        if self.is_periodic:
            if not self.periodic_type or not self.periodic_time:
                raise ValidationError("Planification périodique incomplète.")
        else:
            if self.execute_at and self.execute_at <= timezone.now():
                raise ValidationError("La date d'exécution doit être dans le futur.")

    def __str__(self):
        return f"{self.code} - {self.name}"


# =======================
# 📧 EMAILS LIÉS AU RAPPORT (TO / CC)
# =======================
class ReportEmail(models.Model):

    EMAIL_TYPE_CHOICES = (
        ("to", "TO"),
        ("cc", "CC"),
    )

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="emails"
    )

    email = models.EmailField()
    email_type = models.CharField(
        max_length=2,
        choices=EMAIL_TYPE_CHOICES
    )

    class Meta:
        unique_together = ("report", "email", "email_type")

    def __str__(self):
        return f"{self.report.code} - {self.email} ({self.email_type})"


# =======================
# LOGS D’EXÉCUTION
# =======================
class ReportExecutionLog(models.Model):
    STATUS_CHOICES = (
        ("success", "Succès"),
        ("error", "Erreur"),
    )

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="logs"
    )

    # 🔥 NULL = log global
    query = models.ForeignKey(
        SqlQuery,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="execution_logs"
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES
    )

    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        scope = self.query.name if self.query else "GLOBAL"
        return f"{self.report.name} [{scope}] - {self.status}"


# =======================
# ✅ PARAMÈTRES SQL PAR RAPPORT / REQUÊTE
# =======================
class ReportQueryParameter(models.Model):
    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="query_parameters"
    )

    query = models.ForeignKey(
        SqlQuery,
        on_delete=models.CASCADE,
        related_name="report_parameters"
    )

    name = models.CharField(max_length=100)
    value = models.CharField(max_length=255)

    class Meta:
        unique_together = ("report", "query", "name")

    def __str__(self):
        return f"{self.report.name} - {self.query.name} : {self.name}"



from django.contrib.auth.models import User

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    force_password_change = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username
