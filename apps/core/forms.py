from django.forms.renderers import TemplatesSetting


class BootstrapFormRenderer(TemplatesSetting):
    """Renders every form / field with the project's Bootstrap 5 templates."""

    form_template_name = "forms/form.html"
    field_template_name = "forms/field.html"
