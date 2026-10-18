from django.http import HttpResponseServerError
from django.shortcuts import render
from django.template import loader
from django.views.generic import TemplateView

from apps.appointments.models import Service
from apps.catalog.models import Category, Product


class HomeView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = Product.objects.visible().with_images()
        context["featured_products"] = products.filter(is_featured=True)[:8] or products[:8]
        context["categories"] = Category.objects.active()[:6]
        context["services"] = Service.objects.active()[:6]
        return context


class AboutView(TemplateView):
    template_name = "core/about.html"


class ContactView(TemplateView):
    template_name = "core/contact.html"


def error_404(request, exception):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    # Rendered without context processors: they may hit the database, which
    # could be the very thing that failed.
    return HttpResponseServerError(loader.render_to_string("errors/500.html"))
