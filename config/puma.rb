# © 2026 aiaiaiai · aiaiaiai.org
# SPDX-License-Identifier: MIT
bind "tcp://0.0.0.0:#{ENV.fetch("PORT", "1927")}"
threads 1, 5
workers 0
environment "production"
