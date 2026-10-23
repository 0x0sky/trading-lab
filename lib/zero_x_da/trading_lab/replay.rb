# © 2026 aiaiaiai · aiaiaiai.org
# SPDX-License-Identifier: MIT
# frozen_string_literal: true

require "bigdecimal"
require "time"

module ZeroXDA
  module TradingLab
    class Replay
      DEFAULTS = { "starting_cash" => "1000", "trade_notional" => "100", "fee_bps" => "10", "slippage_bps" => "5", "max_allocation" => "0.25", "max_delay_seconds" => 30 }.freeze

      def self.call(events, options = {})
        new(options).call(events)
      end

      def initialize(options = {})
        raise ArgumentError, "options must be an object" unless options.is_a?(Hash)
        raise ArgumentError, "unknown option" unless (options.keys - DEFAULTS.keys).empty?
        settings = DEFAULTS.merge(options)
        @initial = decimal(settings["starting_cash"], "starting_cash")
        @notional = decimal(settings["trade_notional"], "trade_notional")
        @fee = decimal(settings["fee_bps"], "fee_bps", zero: true) / 10_000
        @slippage = decimal(settings["slippage_bps"], "slippage_bps", zero: true) / 10_000
        @allocation = decimal(settings["max_allocation"], "max_allocation")
        @delay = settings["max_delay_seconds"]
        raise ArgumentError, "invalid fee/slippage/allocation" if @fee >= 1 || @slippage >= 1 || @allocation > 1
        raise ArgumentError, "invalid max_delay_seconds" unless @delay.instance_of?(Integer) && @delay >= 0
      end

      def call(events)
        raise ArgumentError, "events must be an array (maximum 500)" unless events.is_a?(Array) && events.size <= 500
        cash = @initial
        realized = BigDecimal("0")
        positions = {}
        latest = {}
        pending = Hash.new { |h, k| h[k] = [] }
        seen = {}
        fills = []
        rejections = []
        previous = nil
        events.each_with_index do |event, index|
          raise ArgumentError, "event must be an object" unless event.is_a?(Hash)
          at = timestamp(event)
          raise ArgumentError, "event #{index + 1} is out of collection order" if previous && at < previous
          previous = at
          symbol = text(event, "symbol").upcase
          raise ArgumentError, "invalid symbol" unless /\A[A-Z0-9]{5,20}\z/.match?(symbol)
          case text(event, "kind")
          when "signal"
            source, id, side = text(event, "source"), text(event, "id"), text(event, "side").downcase
            raise ArgumentError, "unsupported side" unless %w[buy sell].include?(side)
            raise ArgumentError, "duplicate signal" if seen[[source, id]]
            seen[[source, id]] = true
            pending[symbol] << { "source" => source, "id" => id, "side" => side, "at" => at }
          when "tick"
            mid = decimal(event["price"], "price")
            latest[symbol] = mid
            pending.delete(symbol)&.each do |signal|
              if at - signal["at"] > @delay
                rejections << { "id" => signal["id"], "reason" => "stale_quote" }
                next
              end
              side = signal["side"]
              price = mid * (side == "buy" ? 1 + @slippage : 1 - @slippage)
              if side == "buy"
                if positions.key?(symbol)
                  rejections << { "id" => signal["id"], "reason" => "already_open" }
                  next
                end
                fee = @notional * @fee
                cost = @notional + fee
                if @notional > cash * @allocation || cost > cash
                  rejections << { "id" => signal["id"], "reason" => "risk_limit" }
                  next
                end
                qty = @notional / price
                positions[symbol] = { qty: qty, cost: cost }
                cash -= cost
                pnl = BigDecimal("0")
              else
                position = positions.delete(symbol)
                unless position
                  rejections << { "id" => signal["id"], "reason" => "no_position" }
                  next
                end
                qty = position[:qty]
                fee = qty * price * @fee
                proceeds = qty * price - fee
                cash += proceeds
                pnl = proceeds - position[:cost]
                realized += pnl
              end
              fills << { "id" => signal["id"], "source" => signal["source"], "symbol" => symbol, "side" => side, "received_at" => at.iso8601(6), "price" => num(price), "quantity" => num(qty), "fee" => num(fee), "realized_pnl" => num(pnl) }
            end
          else
            raise ArgumentError, "unsupported event kind"
          end
        end
        equity = positions.reduce(cash) { |sum, (symbol, pos)| sum + pos[:qty] * latest.fetch(symbol) }
        { "initial_cash" => num(@initial), "ending_cash" => num(cash), "equity" => num(equity), "net_pnl" => num(equity - @initial), "realized_pnl" => num(realized), "fills" => fills, "rejections" => rejections, "pending_signals" => pending.values.sum(&:size), "open_positions" => positions.transform_values { |p| num(p[:qty]) } }
      end

      private

      def num(value)
        value.to_s("F")
      end

      def decimal(value, name, zero: false)
        raise ArgumentError, "#{name} must be numeric" if value.nil? || value == true || value == false
        n = BigDecimal(value.to_s)
        raise ArgumentError, "#{name} must be finite and positive" unless n.finite? && (zero ? n >= 0 : n > 0)
        n
      rescue ArgumentError
        raise ArgumentError, "#{name} must be finite and positive"
      end

      def text(event, name)
        value = event[name]
        raise ArgumentError, "#{name} must be a nonempty string" unless value.is_a?(String) && !value.strip.empty?
        value.strip
      end

      def timestamp(event)
        value = text(event, "received_at")
        raise ArgumentError, "timezone is required" unless /(?:Z|[+-]\d{2}:\d{2})\z/i.match?(value)
        Time.iso8601(value).utc
      end
    end
  end
end
