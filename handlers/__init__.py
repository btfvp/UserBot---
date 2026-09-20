from . import help, inline, quote, background, stats, activate


def register_all(app):
    help.register(app)
    inline.register(app)
    quote.register(app)
    background.register(app)
    stats.register(app)
    activate.register(app)

