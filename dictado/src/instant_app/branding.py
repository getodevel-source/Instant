"""Identidad gráfica de Instant, compartida por la ventana y la bandeja."""


def create_icon_image(size=64):
    """Renderiza una marca de micrófono limpia en cualquier tamaño."""
    from importlib import import_module

    Image = import_module("PIL.Image")
    ImageDraw = import_module("PIL.ImageDraw")

    render_size = size * 4
    scale = render_size / 256
    image = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def box(values):
        return tuple(round(value * scale) for value in values)

    background = "#173b49"
    mic = "#72d5c7"
    light = "#f1f6f6"
    draw.rounded_rectangle(
        box((10, 10, 246, 246)), radius=round(54 * scale), fill=background)
    draw.rounded_rectangle(
        box((96, 42, 160, 150)), radius=round(32 * scale), fill=mic)
    stroke = max(1, round(14 * scale))
    draw.line(box((68, 104, 68, 142)), fill=light, width=stroke)
    draw.line(box((188, 104, 188, 142)), fill=light, width=stroke)
    draw.arc(box((68, 82, 188, 202)), start=0, end=180, fill=light, width=stroke)
    draw.rounded_rectangle(
        box((121, 196, 135, 225)), radius=round(7 * scale), fill=light)
    draw.rounded_rectangle(
        box((91, 220, 165, 234)), radius=round(7 * scale), fill=light)
    resampling = getattr(Image, "Resampling", Image)
    return image.resize((size, size), resampling.LANCZOS)
