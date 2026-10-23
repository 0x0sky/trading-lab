# © 2026 aiaiaiai · aiaiaiai.org
# SPDX-License-Identifier: MIT
# frozen_string_literal: true

require "json"
require_relative "replay"

module ZeroXDA
  module TradingLab
    class HTTPApp
      MAX_BYTES = 65_536
      HEADERS = { "content-type" => "application/json; charset=utf-8", "cache-control" => "no-store" }.freeze

      def initialize(token: ENV.fetch("TRADING_LAB_SERVICE_TOKEN"))
        raise ArgumentError, "TRADING_LAB_SERVICE_TOKEN is required" if token.to_s.empty?
        @token = token.to_s
      end

      def call(env)
        return reply(200, status: "ok") if env["REQUEST_METHOD"] == "GET" && env["PATH_INFO"] == "/health"
        return reply(404, error: "not_found") unless env["REQUEST_METHOD"] == "POST" && env["PATH_INFO"] == "/v1/paper/replays"
        authorization = env["HTTP_AUTHORIZATION"].to_s
        provided = authorization.delete_prefix("Bearer ")
        return reply(401, error: "unauthorized") unless authorization.start_with?("Bearer ") && secure_equal?(provided, @token)
        raw = env.fetch("rack.input").read(MAX_BYTES + 1)
        return reply(413, error: "payload_too_large") if raw.bytesize > MAX_BYTES
        document = JSON.parse(raw)
        return reply(422, error: "invalid_request") unless document.is_a?(Hash) && document.key?("events") && (document.keys - %w[events options]).empty?
        reply(200, status: "ok", data: Replay.call(document["events"], document.fetch("options", {})))
      rescue JSON::ParserError
        reply(400, error: "invalid_json")
      rescue ArgumentError, KeyError => error
        reply(422, error: "invalid_request", message: error.message)
      end

      private

      def secure_equal?(a, b)
        return false if a.empty? || a.bytesize != b.bytesize
        a.bytes.zip(b.bytes).reduce(0) { |value, (left, right)| value | (left ^ right) }.zero?
      end

      def reply(status, body)
        [status, HEADERS, [JSON.generate(body)]]
      end
    end
  end
end
