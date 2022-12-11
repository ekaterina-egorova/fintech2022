import copy
import itertools


def cancel_order(placed, timestamp):
    print(f'Cancelled order with id {placed.id} at {timestamp}, was active {(timestamp - placed.placed_timestamp)/1000000} sec')
    placed.state = 'cancel'
    placed.cancelled_timestamp = timestamp


class Context(object):
    passive_lifetime_mc = 10 * 1000 * 1000 # 10 sec
    aggressive_lifetime_mc = 1 * 1000 * 1000 # 1 sec
    part_of_level_amount = 0.01
    amount_trend_multiplier = 2

    def __init__(self, buy_sell, amount):
        self.buy_sell = buy_sell
        self.amount = amount
        self.remaining_amount = amount
        self.avg_execution_price = 0.0
        self.base_plan = []
        self.base_price = None
        self.placed = []
        self.executed = []
        self.our_side_liquidity_history = []
        self.other_side_liquidity_history = []

    def __str__(self):
        return f'Context[buy_sell={self.buy_sell}, ' \
               f'amount={self.amount}, ' \
               f'remaining_amount={self.remaining_amount}, ' \
               f'placed={len(self.placed)}, ' \
               f'executed={len(self.executed)}, ' \
               f'base_price={self.base_price}, ' \
               f'avg_execution_price={self.avg_execution_price}]'
    
    def is_executed(self):
        return 0.001 > self.remaining_amount > -0.001

    def add_executed(self, order): # todo support partial fills, support market orders
        self.executed.append(order)
        self.avg_execution_price = (self.avg_execution_price * (self.amount - self.remaining_amount) + order.price * order.amount)/(self.amount - self.remaining_amount + order.amount)
        self.remaining_amount = self.remaining_amount - order.amount

    def calc_base_plan(self, asks, bids):
        if self.buy_sell == 'buy':
            return get_base_plan_for_amount(self.remaining_amount, asks)
        return get_base_plan_for_amount(self.remaining_amount, bids)

    def calc_base_price(self, asks, bids):
        self.base_plan = self.calc_base_plan(asks, bids)
        self.base_price = calc_avg_price(self.base_plan)

    def calc_trend(self, asks, bids):
        our_side_liquidity = get_all_volume_by_side(self.buy_sell, asks, bids)
        other_side_liquidity = get_all_volume_by_side('sell' if self.buy_sell == 'buy' else 'buy', asks, bids)
        self.our_side_liquidity_history.append(our_side_liquidity)
        self.other_side_liquidity_history.append(other_side_liquidity)

        liq_hist_len = len(self.our_side_liquidity_history)

        if liq_hist_len < 2:
            if our_side_liquidity > other_side_liquidity * 1.01:
                return False
            return True

        # todo clean history, calc on longer data
        our_delta = our_side_liquidity - self.our_side_liquidity_history[liq_hist_len - 2]
        other_delta = other_side_liquidity - self.other_side_liquidity_history[liq_hist_len - 2]

        trend = True if our_delta > other_delta else False
        #print(f'best_ask={asks[0][0]}, best_bid={bids[0][0]}, our_side_liq={our_side_liquidity}, other_side_liq={other_side_liquidity}, our_delta={our_delta}, other_delta={other_delta}, trend={"positive" if trend else "negative"}')
        return trend

    def calc_amount_trend(self, asks, bids):
        cur_price = asks[0][0] if self.buy_sell == 'buy' else bids[0][0]
        if self.buy_sell == 'buy' and cur_price < self.base_price:
            return Context.amount_trend_multiplier * (self.base_price / cur_price)
        if self.buy_sell == 'sell' and cur_price > self.base_price:
            return Context.amount_trend_multiplier * (cur_price / self.base_price)

        return 1
    
    def calc_order_values(self, asks, bids):
        amount_trend = self.calc_amount_trend(asks, bids)
        is_good_price_trend = self.calc_trend(asks, bids)

        best_level = asks[0]
        if (is_good_price_trend and self.buy_sell == 'buy') or (not is_good_price_trend and self.buy_sell == 'sell'):
            best_level = bids[0]

        price = best_level[0]
        amount = self.remaining_amount \
            if self.remaining_amount < best_level[1] * amount_trend * Context.part_of_level_amount \
            else best_level[1] * amount_trend * Context.part_of_level_amount
        
        return price, amount, 'passive' if is_good_price_trend else 'aggressive'

    def count_placed_orders(self):
        count = 0
        for order in self.placed:
            if order.state =='placed':
                count = count + 1
        return count
    
    def place_order(self, timestamp, price, amount, aggressive_passive):  
        order = Order(self.buy_sell, amount, price, 
                      aggressive_passive, 
                      'limit', 'placed', timestamp, 
                      timestamp  + (Context.passive_lifetime_mc if aggressive_passive == 'passive' else Context.aggressive_lifetime_mc))
        self.placed.append(order)
        print(f'Placed {order}')
        return order

    def execute_orders(self, asks, bids, timestamp):
        _asks = copy.deepcopy(asks)
        _bids = copy.deepcopy(bids)

        for order in self.placed:
            if order.order_type != 'limit':
                raise NotImplementedError()  # todo support market do not execute worse than cur price
            if order.state != 'placed':
                continue

            executed = try_execute(order, bids[0]) if order.buy_sell == 'buy' else try_execute(order, asks[0])

            if executed is not None:
                executed.execution_asks = _asks
                executed.execution_bids = _bids
                executed.executed_timestamp = timestamp
                self.add_executed(executed)
                print(f'Executed {order.buy_sell} order with id {executed.id} on price {executed.price}, ask={_asks[0][0]}, bid={_bids[0][0]}')
                #print(self)

        return True
    
    def cancel_good_till(self, timestamp):
        cancelled = []
        for placed in self.placed:
            if placed.state == 'placed' and placed.good_till_timestamp < timestamp:
                cancel_order(placed, timestamp)
                cancelled.append(placed)
        return cancelled

    def cancel_all_orders(self, timestamp):
        cancelled = []
        for placed in self.placed:
            if placed.state == 'placed':
                cancel_order(placed, timestamp)
                cancelled.append(placed)
        return cancelled


class Order(object):
    id_seq = itertools.count()

    def __init__(self, buy_sell, amount, price, aggressive_passive, order_type, state, 
                 placed_timestamp = None, good_till_timestamp = None, executed_timestamp = None, cancelled_timestamp = None):
        self.id = next(Order.id_seq)
        self.buy_sell = buy_sell
        self.amount = amount
        self.price = price
        self.aggressive_passive = aggressive_passive
        self.order_type = order_type
        self.state = state
        self.execution_asks = []
        self.execution_bids = []
        self.placed_timestamp = placed_timestamp
        self.executed_timestamp = executed_timestamp
        self.cancelled_timestamp = cancelled_timestamp
        self.good_till_timestamp = good_till_timestamp

    def __str__(self):
        return f'Order[id={self.id}, buy_sell={self.buy_sell}, amount={self.amount}, price={self.price}, ' \
               f'aggressive_passive={self.aggressive_passive}, type={self.order_type}, ' \
               f'state={self.state}, ' \
               f'placed_timestamp={self.placed_timestamp}, ' \
               f'good_till_timestamp={self.good_till_timestamp}, ' \
               f'executed_timestamp={self.executed_timestamp}, ' \
               f'cancelled_timestamp={self.cancelled_timestamp}]'

def subscribe_on_prices(context, prices_csv_file_name, start_timestamp = None, end_timestamp = None):
    with open(prices_csv_file_name) as file:
        next(file) # skip headers

        for line in file: # gather some data to understand trends
            timestamp, asks, bids = parse_line(line)
            if start_timestamp is None:
                start_timestamp = timestamp

            if start_timestamp > timestamp:
                continue

            context.calc_trend(asks, bids)

            if timestamp > start_timestamp + 10000000: # 10 sec
                context.calc_base_price(asks, bids)
                break

        i = 0
        for line in file:
            timestamp, asks, bids = parse_line(line)

            context.execute_orders(asks, bids, timestamp)

            context.cancel_good_till(timestamp)

            if context.is_executed():
                context.cancel_all_orders(timestamp)
                print(f'Order completely executed in {i + 1} ticks')
                return

            if end_timestamp is not None and end_timestamp < timestamp:
                context.cancel_all_orders(timestamp)
                print(f'Time is up end_timestamp={end_timestamp}, timestamp = {timestamp}')
                return

            if context.count_placed_orders() == 0:
                price, amount, aggressive_passive = context.calc_order_values(asks, bids)
                context.place_order(timestamp, price, amount, aggressive_passive)

            i = i + 1


def parse_line(line):
    asks = []
    bids = []
    # asks[0].price,asks[0].amount,bids[0].price,bids[0].amount,asks[1].pri
    tokens = line.split(',')

    for i in range(4, len(tokens) - 4, 4):
        asks.append((float (tokens[i]), float(tokens[i+1])))
        bids.append((float (tokens[i+2]), float(tokens[i+3])))

    return int (tokens[2]), asks, bids

def execute_huge_order(buy_sell, amount, prices_csv_file_name, start_timestamp = None, end_timestamp = None):
    print(f'Executing huge order {buy_sell} {amount} BTC')
    context = Context(buy_sell, amount)
    subscribe_on_prices(context, prices_csv_file_name, start_timestamp, end_timestamp)
    return context


def get_base_plan_for_amount(remaining_amount, prices):
    orders = []
    remaining = remaining_amount
    i = 0
    while remaining > 0 and i < len(prices):
        p = prices[i]
        amount = min(remaining, p[1])
        order = Order('buy', amount, p[0], 'aggressive', 'limit', None)
        orders.append(order)

        remaining = remaining - amount
        i = i + 1
    return orders

def calc_avg_price(plan):
    avg_price = 0.0
    executed_amount = 0.0
    for row in plan:
        avg_price = (avg_price * executed_amount + row.price * row.amount)/(executed_amount + row.amount)
        executed_amount = executed_amount + row.amount
    return avg_price

def get_volume(orders):
    volume = 0.0
    for order in orders:
        volume = volume + order[1]
    return volume

def get_all_volume_by_side(buy_sell, asks, bids):
    if buy_sell == 'buy':
        return get_volume(asks)
    return get_volume(bids)

def try_execute(order, other_side_best_level):
    if (order.buy_sell == 'buy' and order.price > other_side_best_level[0])\
            or (order.buy_sell == 'sell' and order.price < other_side_best_level[0]):
        order.state = 'executed'
        return order
    return None

# timestamps in mc
execution_context = execute_huge_order('buy', 400000, 'deribit_book_snapshot_25_2020-04-01_BTC-PERPETUAL.csv') #, start_timestamp=1585699201275000, end_timestamp=1585699201275000 + 300000000) # 5 min
print(execution_context)

#print('Execution list:')
#print(*execution_context.executed)

#print('Order book on execution:')
#print(*execution_context.executed[0].execution_asks)
#print(*execution_context.executed[0].execution_bids)

