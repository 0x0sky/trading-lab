# © 2026 aiaiaiai · aiaiaiai.org
# SPDX-License-Identifier: MIT
# frozen_string_literal: true
require "bundler/setup"
require_relative "lib/zero_x_da/trading_lab/http_app"
run ZeroXDA::TradingLab::HTTPApp.new
