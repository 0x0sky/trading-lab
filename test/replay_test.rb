# © 2026 aiaiaiai · aiaiaiai.org
# SPDX-License-Identifier: MIT
# frozen_string_literal: true

require "minitest/autorun"
require "bigdecimal"
require "stringio"
require "json"
require_relative "../lib/zero_x_da/trading_lab/replay"
require_relative "../lib/zero_x_da/trading_lab/http_app"

class TradingLabTest < Minitest::Test
  T0 = "2026-10-23T10:00:00+00:00"
  T1 = "2026-10-23T10:00:01+00:00"
  T2 = "2026-10-23T10:00:02+00:00"

  def signal(id, at, side = "buy", source: "channel")
    { "kind" => "signal", "id" => id, "source" => source, "side" => side, "symbol" => "BTCUSDT", "received_at" => at }
  end

  def tick(at, price = "100")
    { "kind" => "tick", "price" => price, "symbol" => "BTCUSDT", "received_at" => at }
  end

  def replay(events, options = {})
    ZeroXDA::TradingLab::Replay.call(events, options)
  end

  def test_round_trip
    events = [signal("a", T0), tick(T1), signal("b", T1, "sell"), tick(T2, "110")]
    result = replay(events, { "fee_bps" => "0", "slippage_bps" => "0" })
    assert_equal BigDecimal("10"), BigDecimal(result.fetch("realized_pnl"))
    assert_equal 2, result.fetch("fills").size
    assert_equal({}, result.fetch("open_positions"))
    assert_operator BigDecimal(replay(events).fetch("net_pnl")), :<, BigDecimal(result.fetch("net_pnl"))
  end

  def test_no_lookahead
    result = replay([tick(T0), signal("a", T1)])
    assert_empty result.fetch("fills")
    assert_equal 1, result.fetch("pending_signals")
  end

  def test_stale_tick
    result = replay([signal("a", T0), tick("2026-10-23T10:00:31+00:00")])
    assert_equal "stale_quote", result.fetch("rejections").first.fetch("reason")
  end

  def test_duplicates
    assert_raises(ArgumentError) { replay([signal("a", T0), signal("a", T1)]) }
    result = replay([signal("a", T0), signal("a", T1, "buy", source: "other"), tick(T2)])
    assert_equal "already_open", result.fetch("rejections").first.fetch("reason")
  end

  def test_no_shorts_or_overallocation
    assert_equal "no_position", replay([signal("a", T0, "sell"), tick(T1)]).fetch("rejections").first.fetch("reason")
    assert_equal "risk_limit", replay([signal("a", T0), tick(T1)], { "starting_cash" => "100" }).fetch("rejections").first.fetch("reason")
  end

  def test_malformed_events_fail_closed
    assert_raises(ArgumentError) { replay([tick(T2), tick(T0)]) }
    assert_raises(ArgumentError) { replay([tick("2026-10-23T10:00:00")]) }
    assert_raises(ArgumentError) { replay([tick(T0, "NaN")]) }
    assert_raises(ArgumentError) { replay([], { "fee_bps" => "-1" }) }
    assert_raises(ArgumentError) { replay([], { "max_delay_seconds" => true }) }
    assert_raises(ArgumentError) { replay(Array.new(501) { tick(T0) }) }
  end

  def request(body: '{"events":[]}', token: "test-secret", path: "/v1/paper/replays", method: "POST")
    app = ZeroXDA::TradingLab::HTTPApp.new(token: "test-secret")
    status, _, output = app.call("REQUEST_METHOD" => method, "PATH_INFO" => path,
                                 "HTTP_AUTHORIZATION" => "Bearer #{token}", "rack.input" => StringIO.new(body))
    [status, JSON.parse(output.join)]
  end

  def test_private_service_contract
    assert_equal 401, request(token: "wrong").first
    assert_equal 200, request.first
    assert_equal 413, request(body: "{" + "x" * 65_537).first
    assert_equal 400, request(body: "no-json").first
    assert_equal 422, request(body: '{"events":"bad"}').first
    assert_equal 404, request(path: "/live/orders").first
    assert_equal 200, request(path: "/health", method: "GET", token: "").first
  end
end
