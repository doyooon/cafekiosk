from typing import Dict, Text, Any, List, Union
from rasa_sdk import Action, Tracker
from rasa_sdk.forms import FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet,FollowupAction,AllSlotsReset,Restarted,ActiveLoop

import random

from . import TABLE

ORDER_REQUIRED_ENTITY = ["menu","count","size","temp"] #음료 주문을 위한 필수 엔테티

class order_queue(Action): # "주문 부터 시작하는 경우"
    def name(self):
        return "action_order_queue"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        entities = tracker.latest_message['entities']
        orders = {}

        # 주문 정보를 그룹별로 수집
        for entity in entities:
            group = entity.get("group")
            if group is not None:
                if group not in orders: orders[group] = {}
                orders[group][entity["entity"]] = entity["value"]

        not_menu_orders = [] # 메뉴가 누락된 주문은 무시
        undefined_menu = [] # 메뉴목록에 없는 메뉴는 주문을 받지 않음
        for grp,order in orders.items():
            if "menu" not in order:not_menu_orders.append(grp) # 메뉴 엔터티 추출에 실패한 경우
            else:
                before = order['menu']
                _menu = _valid(order['menu'],"menu")
                if _menu is None:
                    undefined_menu.append(grp)
                    dispatcher.utter_message(text=f"{before}란 메뉴는 저희 매장에서 판매하지 않아요")
                order["menu"] = _menu 
                
        for grp in set(not_menu_orders):
            _ = orders.pop(grp)
        for grp in set(undefined_menu):
            order = orders.pop(grp)

        for grp,order in orders.items():
            menu = order['menu']
            menu_temp = drink_temp(menu)

            if 'temp' not in order or order['temp'] is None:
                order['temp'] = menu_temp
            # if menu_category in ['juice','ade','smoothie']:
            #     order['temp'] = '아이스'
            # elif menu == '핫초코':
            #     order['temp'] = 'hot'

        # 이미 주문한 정보를 저장
        events = []
        if orders:
            first_grp = next(iter(orders))
            first_order = orders.pop(first_grp)
            before = {}
            for key in ORDER_REQUIRED_ENTITY:
                if key in first_order:
                    events.append(SlotSet(key,first_order[key]))
                    before[key] = first_order[key]
                else:
                    events.append(SlotSet(key,None))
                    before[key] = None
            
            events.append(SlotSet("before",[before])) # 현재 주문은 before에 맵핑해주길 바래

            #추가 주문이 남아 있는 경우
            if orders:
                order_queue = list(orders.values())
                events.append(SlotSet("order_queue",order_queue))
    
        else: # 주문이 아예 엾는 경우
            if len(undefined_menu) == 0 : dispatcher.utter_message(text=f"잘 이해하지 못했어요. 다시 말씀해주세요")
            events += [AllSlotsReset(),Restarted()]

        ordered_queue = tracker.get_slot("ordered_queue")
        events.append(SlotSet("ordered_queue",ordered_queue))
        
        return events
    
class provide_info_with_order_drink(Action): # "order drink로 추가 정보를 채우는 경우"
    def name(self):
        return "action_fill_slot_with_order_drink"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        entities = tracker.latest_message['entities']
        orders = {}

        current_order = tracker.get_slot("before")
        if current_order is None or len(current_order) == 0:
            dispatcher.utter_message(text=f"죄송합니다. 말씀을 잘 이해햐지 못했어요")
            return []
        else: current_order = current_order[0]
        # current_order = {entity : tracker.get_slot(entity) for entity in ORDER_REQUIRED_ENTITY} # 현재 주문하고 있는 메뉴 정보 
        order_queue = tracker.get_slot('order_queue') #후에 처리 해야할 정보

        for entity in entities:
            group = entity.get("group")
            if group is None: continue
            if entity['entity'] == 'menu':
                val = before = entity['value']
                val = _valid(val,'menu')

                if val is None:
                    dispatcher.utter_message(text=f"{before}란 메뉴는 판매하지 않습니다")
                else:
                    if group in orders: orders[group]['menu'] = val
                    else: orders[group] = {'menu' : val}
            else:
                val = entity['value']
                val = _valid(val, entity['entity'])
                
                if val is None:
                    dispatcher.utter_message(text=f"죄송합니다. 말씀을 잘 이해햐지 못했어요")
                    return []
                else:
                    if group in orders: orders[group][entity['entity']] = val
                    else: orders[group] = {entity['entity'] : val}

        _orders = []
        for grp,order in orders.items():
            if 'menu' not in order or order['menu'] is None:
                if grp is '1':  order['menu'] = current_order['menu']
            _orders.append(order)

        #정보 끼워넣기
        current_check = False
        print(_orders)
        for order in _orders:
            matched = False  
            if not current_check and order['menu'] == current_order['menu']:  # 현재 처리 하는 주문에 끼워넣을수있느니 확인
                want_to_cng,search_key = [],True
                for e,val in current_order.items():
                    if e == 'menu': continue
                    if val is not None and e in order and val != order[e]: #이미 채워져 있고 그걸 바꿀려고 함
                        search_key = False
                        break
                    if val is None and e in order and order[e] is not None:
                        want_to_cng.append(e) # 이 엔터티로 집어 넣을 수 있음
                 
                if search_key:
                    for e in want_to_cng:
                        current_order[e] = order[e]
                    matched = True
                    current_check = True
            
            if matched:  continue
            # 혹시 queue에 있는 정보에 해당하는가?
            if order_queue is not None and len(order_queue) != 0: # 혹시나 이미 주문한걸 찾는지 탐색
                for i,queue_order in enumerate(order_queue):
                    if order['menu'] != queue_order['menu']: continue
                    want_to_cng,search_key = [],True
                    for e,val in order.items():
                        if e == 'menu' : continue
                        if e in queue_order and e is not None and queue_order[e] is not None and val != queue_order[e]:
                            search_key = False
                            break
                        if e not in queue_order or queue_order[e] is None:
                            want_to_cng.append(e)
                    if search_key:
                        for e in want_to_cng:
                            order_queue[i][e] = order[e]
                            print('change',want_to_cng)
                        matched = True
                        break
            
            # 아니면 새로운 음료를 추가하는 것!
            if not matched:
                order['temp'] = drink_temp(order['menu'])
                if order_queue is None or len(order_queue) == 0: order_queue = [order]
                else: order_queue.append(order)

        
    
        # Slot mapping
        events = [SlotSet(entity,current_order[entity]) for entity in ORDER_REQUIRED_ENTITY]
        events.append(SlotSet("before",[current_order]))
        events.append(SlotSet("order_queue",order_queue))

        return events      

class order_queue_next(Action):
    def name(self):
        return "action_order_queue_next"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        order_queue = tracker.get_slot("order_queue")
        if not order_queue:
            # 주문 큐가 비어 있으면 더 이상 처리할 주문이 없음
            return []

        # 첫번째 주문을 슬롯에 설정
        events = []
        events.append(Restarted())
        first_order = order_queue.pop(0)  # 첫 번째 주문을 꺼내고 나머지 주문을 업데이트
        events.append(SlotSet("order_queue", order_queue if order_queue else None)) # 남은 주문 업데이트

        before = {}
        for entity in ORDER_REQUIRED_ENTITY:
            if entity in first_order:
                events.append(SlotSet(entity, first_order[entity]))
                before[entity] = first_order[entity]
            else:
                events.append(SlotSet(entity,None))
                before[entity] = None

        events.append(SlotSet("before",before))
        ordered_queue = tracker.get_slot("ordered_queue")
        events.append(SlotSet("ordered_queue",ordered_queue))

        events.append(FollowupAction("order_form"))
        return events

class submit_order(Action):
    def name(self):
        return "action_submit_order"

    def run(self, dispatcher, tracker, domain):
        # 슬롯에서 데이터 추출
        menu = tracker.get_slot('menu')
        size = tracker.get_slot('size')
        count = tracker.get_slot('count')
        temp = tracker.get_slot('temp')

        # 데이터를 JSON 형태로 가공
        order_details = {
            "menu": menu,
            "size": size,
            "count": count,
            "temp": temp
        }
        fill_check = True
        for entity in ORDER_REQUIRED_ENTITY:
            if order_details[entity] is None:
                fill_check = False
                break
    
        ordered_queue = tracker.get_slot('ordered_queue')

        if fill_check:
            if ordered_queue is None: ordered_queue = [order_details]
            else: ordered_queue.append(order_details)

        order_queue = tracker.get_slot("order_queue")
        if order_queue:
            return [SlotSet("ordered_queue",ordered_queue),FollowupAction("action_order_queue_next")]
        elif fill_check:
            dispatcher.utter_message(text="추가로 더 주문하시겠어요, 아니면 결제를 진행할까요?")
            return [AllSlotsReset(),SlotSet("ordered_queue",ordered_queue)]

# @app.route("/order", methods=['GET'])
# def get_order():
#     return order_details

class validate_order_form(FormValidationAction):
    def name(self) -> Text:
        return "validate_order_form"

    def validate_count(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text,Any],

    ) -> Dict[Text,Any]:
        value = _valid(value,"count")
        before = tracker.get_slot('before')
        if value is not None and before is not None and len(before) != 0:
            before = before[0]
            before['count'] = value
            return {"count" : value, 'before' : [before]}
        return {"count" : value}

    def validate_temp(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text,Any],

    ) -> Dict[Text,Any]:
        value = _valid(value,"temp")
        before = tracker.get_slot('before')
        if value is not None and before is not None and len(before) != 0:
            before = before[0]
            before['temp'] = value
            return {"temp" : value, 'before' : [before]}
        return {"temp" : _valid(value,"temp")}

    def validate_size(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text,Any],

    ) -> Dict[Text,Any]:
        value = _valid(value,"size")
        before = tracker.get_slot('before')
        if value is not None and before is not None and len(before) != 0:
            before = before[0]
            before['size'] = value
            return {"size" : value, 'before' : [before]}
        return {"size" : _valid(value,"size")}


class change_order(Action):
    def name(self):
        return "action_change_order"
    
    def run(self,dispatcher,tracker,domain):
        entities = tracker.latest_message['entities']

        before = tracker.get_slot('before')
        form_flag = False
        if before is not None and len(before) != 0: form_flag = True

        events = []
        if entities is None: # 인텐트를 잘못 분류했거나 엔테티를 하나도 추출하지 못한 경우
            dispatcher.utter_message(text="잘 이해하지 못했어요. 변경하시려는 메뉴와 변경 내용을 다시 말씀해주세요")

            if form_flag:
                events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                events.append(ActiveLoop("order_form"))

            return events
        
        ordered_list = tracker.get_slot('ordered_queue')
        e_dict = {'from' : {}, 'to' : {}}
        for entity in entities: # 엔테티 추출 및 검증
            entity_name = entity.get('entity')
            role = entity.get('role','from')
            if entity_name == 'menu':
                e_dict[role]['menu'] = entity.get('value')
                continue
            val = _valid(entity.get('value'),entity_name) # 미리 검증
            if val is None: # 옵션을 이해하지 못한 경우
                dispatcher.utter_message(text="잘 이해하지 못했어요. 변경하시려는 메뉴와 변경 내용을 다시 말씀해주세요")

                if form_flag:
                    events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                    events.append(ActiveLoop("order_form"))
                return events
            
            e_dict[role][entity_name] = val   
        
        if 'menu' not in e_dict['from']: # 변경하려는 메뉴를 인식하지 못한 경우
            dispatcher.utter_message(text="잘 이해하지 못했어요. 변경하시려는 메뉴와 변경 내용을 함께 말씀해주세요")

            if form_flag:
                events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                events.append(ActiveLoop("order_form"))

            return events

        # 메뉴를 변경한다면, 메뉴 검증
        if 'menu' in e_dict['to']:
            before = e_dict['to']['menu']
            e_dict['to']['menu'] = _valid(e_dict['to']['menu'],'menu')
            ########## 아이스 체크 하기 ###############
            if e_dict['to']['menu'] is None:
                dispatcher.utter_message(text=f"{before}라는 메뉴는 저희 매장에서 판매하지 않아요")
            
            
        
        # 변경해야하는 주문을 검색
        search_key = have_to_cng = e_dict['from']
        ordered = -1
        for i,order in enumerate(ordered_list):
            find = True
            for key,val in search_key.items():
                if key == "count" : continue
                if val != order[key]:
                    find = False
                    break
            if find:
                ordered = i
                break

        if ordered == -1: # 변경해야하는 주문을 찾지 못함.
            dispatcher.utter_message(text="변경하려는 주문을 찾지 못했어요. 주문내역을 확인하시거나 다시 말씀해주세요")

            if form_flag:
                events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                events.append(ActiveLoop("order_form"))
            return events

        ordered = ordered_list.pop(ordered)
        
        want_to_cng = e_dict['to']

        # 핫 -> 아이스로 변경해야하는 경우 처리
        if 'menu' in want_to_cng:
            temp = drink_temp(want_to_cng['menu'])
            want_to_cng['temp'] = temp
            ordered['temp'] = temp

        if 'count' in have_to_cng and 'count' in want_to_cng: # have_to_cng count 취소후 want_to_cng로 변경 (3잔 중 하나를 변경 등...) -> want_to_cng 기준으로 동작
            new_order = {}
            ordered['count'] = str(max(int(ordered['count']) - int(want_to_cng['count']),0))
            new_order['count'] = want_to_cng['count']
            for key in ORDER_REQUIRED_ENTITY:
                if key == 'count': continue
                if key in want_to_cng: new_order[key] = want_to_cng[key]
                else: new_order[key] = ordered[key]
            
        elif 'count' in have_to_cng and 'count' not in want_to_cng: # have_to_cng count 취소 후 동일한 count로 메뉴 변경 (아메리카노 2잔을 카페라떼로 변경해주세요) 
            new_order = {} 
            ordered['count'] = str(int(ordered['count']) - int(have_to_cng['count']))
            new_order['count'] = have_to_cng['count']

            for key in ORDER_REQUIRED_ENTITY:
                if key == 'count': continue
                if key in want_to_cng: new_order[key] = want_to_cng[key]
                else: new_order[key] = ordered[key]
            
        elif 'count' not in have_to_cng and 'count' in want_to_cng: # ordered 전체 취소 후 count에 맞게 수정 (아메리카노를 카페라떼 2잔으로 변경해주세요)
            new_order = {}
            ordered['count'] = str(max(int(ordered['count']) - int(want_to_cng['count']),0))
            new_order['count'] = want_to_cng['count']

            for key in ORDER_REQUIRED_ENTITY:
                if key == 'count': continue
                if key in want_to_cng: new_order[key] = want_to_cng[key]
                else: new_order[key] =ordered[key]
        else: 
            new_order = {}
            for key in ORDER_REQUIRED_ENTITY:
                if key in want_to_cng: new_order[key] = want_to_cng[key]
                else: new_order[key] = ordered[key]
            
            ordered['count'] = '0' # 기존 주문이 사라짐

        if ordered['count'] != '0': ordered_list.append(ordered)
        ordered_list.append(new_order)

        dispatcher.utter_message(text="주문이 변경돼었어요")

        if form_flag:
            events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
            events.append(ActiveLoop("order_form"))
        
        events.append(SlotSet('ordered_queue',ordered_list))
        
        return events

class cancel_order(Action):
    def name(self):
        return "action_cancel_order"
    
    def run(self,dispatcher,tracker,domain):
        entities = tracker.latest_message['entities']
        ordered_list = tracker.get_slot('ordered_queue')

        cancels = {
            'from' : {},
            'to' : {}
        }

        events = []
        before = tracker.get_slot('before')
        form_flag = False
        if before is not None and len(before) != 0: form_flag = True

        if len(entities) == 0 or entities is None:
            dispatcher.utter_message(text="모든 주문이 취소 되었어요")
            events.append(SlotSet('ordered_queue',None))

            if form_flag:
                events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                events.append(ActiveLoop("order_form"))

            return events

        for entity in entities:
            group = entity.get("group")
            role = entity.get('role','from')

            if group is not None:
                val = entity['value']
                if entity['entity'] == 'menu': val = val.replace(" ","")
                else: val = _valid(val,entity['entity'])

                if val == None:
                    dispatcher.utter_message(text="죄송합니다. 잘 이해하지 못했어요. 다시 말씀해주세요")

                    if form_flag:
                        events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                        events.append(ActiveLoop("order_form"))
                    return events
                             
                if group not in cancels[role]: cancels[role][group] = {}
                cancels[role][group][entity['entity']] = val

        '''
        to가 있는 경우 to 기준으로만 삭제를 처리
        to의 메뉴가 없는 경우 -> group 을 사용해서, from의 정보로 주문 목록에서 조회 후 to를 반영
        '''
        if len(cancels['to']) != 0:
            for group,cancel_item in cancels['to'].items():

                if 'menu' not in cancel_item: # 카페라떼(from) 두잔(from) 시켰는데 이중 한잔(to)은 취소 해주세요
                    search_key = cancels['from'][group]
                    cmenu = cancels['from'][group]['menu']
                else:
                    search_key = cancel_item
                    cmenu = cancel_item['menu']

                # 삭제해야할 메뉴 찾기
                target = -1
                for i,order in enumerate(ordered_list):
                    find = True
                    for key,val in search_key.items():
                        if key == 'count': continue
                        if val != order[key]:
                            find = False
                            break
                    if find:
                        target = i
                        break
                
                if target == -1:
                    dispatcher.utter_message(text="죄송합니다. 취소하시려는 주문을 주문내역에서 찾을 수 없어요")

                    if form_flag:
                        events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                        events.append(ActiveLoop("order_form"))
                    return events

                target = ordered_list.pop(target)
                if 'count' in cancel_item:
                    target['count'] = str(max(int(target['count']) - int(cancel_item['count']),0))
                    dispatcher.utter_message(text=f"{cmenu} {cancel_item['count']}잔이 취소되었습니다")

                    if target['count'] != '0': ordered_list.append(target)
                else: dispatcher.utter_message(text=f"{cmenu}가 취소되었습니다")

        else: # to가 없는 경우 from을 전부 삭제하면 됌
            for group,cancel_item in cancels['from'].items():
                if 'menu' not in cancel_item:
                    dispatcher.utter_message(text="죄송합니다. 취소하시려는 주문을 주문내역에서 찾을 수 없어요")
                    return events

                # 삭제해야할 메뉴 찾기
                target = -1
                if ordered_list is not None and len(ordered_list) != 0:
                    for i,order in enumerate(ordered_list):
                        find = True
                        for key,val in cancel_item.items():
                            if key == 'count' : continue
                            if val != order[key]:
                                find = False
                                break
                        if find:
                            target = i
                            break
                
                if target == -1:
                    dispatcher.utter_message(text="죄송합니다. 취소하시려는 주문을 주문내역에서 찾을 수 없어요")


                    if form_flag:
                        events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                        events.append(ActiveLoop("order_form"))
                    return events

                target = ordered_list.pop(target)
                if 'count' in cancel_item:
                    target['count'] = str(max(int(target['count']) - int(cancel_item['count']),0))
                    dispatcher.utter_message(text=f"{cancel_item['menu']} {cancel_item['count']}잔이 취소되었습니다")

                    if target['count'] != '0': ordered_list.append(target)
                else: dispatcher.utter_message(text=f"{cancel_item['menu']}가 취소되었습니다")

        events.append(SlotSet('ordered_queue',ordered_list))
        
        if form_flag:
            events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
            events.append(ActiveLoop("order_form"))
        return events
    
class ask_ordered(Action): # 자신의 주문 내역을 확인
    def name(self):
        return "action_q_order"

    def run(self, dispatcher, tracker, domain):
        ordered_list = tracker.get_slot('ordered_queue')

        if ordered_list is None or len(ordered_list) == 0:
            dispatcher.utter_message(text="주문 내역이 비었습니다")
            return []
        else:
            string = ""
            for i,order in enumerate(ordered_list):
                category = drink_to_category(order['menu'])
                if category not in ['juice','ade','smoothie']:
                    s  = f"{order['size']}사이즈 {order['temp']} {order['menu']} {order['count']}잔"
                else:
                    s  = f"{order['size']}사이즈 {order['menu']} {order['count']}잔"
                if i == len(ordered_list) - 1:
                    string += s
                else:
                    string += f'{s}, '
            
            dispatcher.utter_message(text=f"{string}이 주문 되었습니다")
            return []
        
class ask_menu(Action): # 이런 메뉴 파나요?
    def name(self):
        return "action_ask_menu"

    def run(self,dispatcher,tracker,domain):
        entities = tracker.latest_message['entities']

        asks = {}
        not_sell_cnt = 0
        for entity in entities:
            group = entity.get("group")
            if entity['entity'] == 'menu' and group is not None:
                val = before = entity['value']
                val = _valid(val,'menu')

                if val is None:
                    dispatcher.utter_message(text=f"{before}란 메뉴는 판매하지 않습니다")
                    not_sell_cnt += 1
                else:
                    dispatcher.utter_message(text=f"네 저희 매장은 {val}를 판매하고 있어요")
                    asks[group] = {'menu' : val}

        events = [SlotSet(entity,None) for entity in ORDER_REQUIRED_ENTITY]


        before = tracker.get_slot('before')
        if before is not None and len(before) != 0:
            events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
            events.append(ActiveLoop("order_form"))

        if len(asks) >= 1:
            events.append(SlotSet("asked_queue",list(asks.values())))
            return events
        elif len(asks) == 0 and not_sell_cnt == 0:
            dispatcher.utter_message(text="죄송합니다. 말씀을 이해하지 못했어요") 
        
        return events

class ask_price(Action): #가격 확인
    def name(self):
        return "action_q_price"

    def run(self, dispatcher, tracker, domain):
        latest_user_message = None
        for event in reversed(tracker.events):
            if event.get('event') == 'user':
                latest_user_message = event.get('text')
                break

        events = [SlotSet(entity,None) for entity in ORDER_REQUIRED_ENTITY]

        before = tracker.get_slot('before')
        form_flag = False
        if before is not None and len(before) != 0: form_flag = True

        if latest_user_message is None:
            dispatcher.utter_message(text="죄송합니다. 잘 이해하지 못했어요. 다시 말씀해주세요")

            if form_flag:
                events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                events.append(ActiveLoop("order_form"))
            return events 

        entities = tracker.latest_message['entities']
        if len(entities) == 0:
            if '크기' in latest_user_message or '사이즈' in latest_user_message:
                dispatcher.utter_message(text="사이즈업 할때마다 500원이 추가돼요")
                if form_flag:
                    events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                    events.append(ActiveLoop("order_form"))
                return events
        
        ordered_list = tracker.get_slot('ordered_queue')

        # 주문 정보를 그룹별로 수집
        asks = {}
        skip_group = set()
        for entity in entities:
            group = entity.get("group")
            if group is not None and group not in skip_group:
                val = entity['value']
                if entity['entity'] == 'menu':
                    before = val
                    val = _valid(val,"menu")
                    if val is None:
                        skip_group.add(group)
                        dispatcher.utter_message(text=f"{before}란 메뉴는 판매하지 않습니다")
                        continue
                else:
                    val = _valid(val,entity['entity'])
                
                if val is None:
                    dispatcher.utter_message(text="죄송합니다. 잘 이해하지 못했어요. 다시 말씀해주세요")
                    if form_flag:
                        events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                        events.append(ActiveLoop("order_form"))
                    return events

                if group not in asks: asks[group] = {}
                asks[group][entity['entity']] = val  

        for grp in skip_group:
            if grp in asks: asks.pop(grp)

        if len(asks) == 0 and len(skip_group) != 0:
            dispatcher.utter_message(text="죄송합니다. 잘 이해하지 못했어요. 다시 말씀해주세요")
            if form_flag:
                events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                events.append(ActiveLoop("order_form"))
            return events

        if len(asks) == 0 and len(skip_group) == 0: # no group, no intent -> 내가 주문한 가격을 물어보는 것
            latest_user_message = latest_user_message.replace(" ","")
            size_flag = None
            for same,size in TABLE.size_to_category.items():
                if same in latest_user_message:
                    size_flag = None
                    break
            print(latest_user_message)
            if size_flag is None and ('사이즈' in latest_user_message or '크기' in latest_user_message): size_flag = True
            if size_flag is not None:
                if size_flag is '스몰' : dispatcher.utter_message(text=f"기본 사이즈는 스몰이고 추가 금액은 없어요")
                elif size_flag is '미디움' : dispatcher.utter_message(text=f"중간 사이즈는 500원이 추가되요")
                elif size_flag is '라지' : dispatcher.utter_message(text=f"라지 사이즈는 1000원이 추가 됩니다")
                else: dispatcher.utter_message(text=f"기본 사이즈는 스몰이고 미디움 사이즈는 500원 라지 사이즈는 1000원이 추가돼요")

                if form_flag:
                    events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                    events.append(ActiveLoop("order_form"))
                return events
            elif len(skip_group) == 0:
                ordered_list = tracker.get_slot('ordered_queue')
                if ordered_list is None or len(ordered_list) == 0:
                    dispatcher.utter_message(text=f"주문 내역이 비었습니다")

                    if form_flag:
                        events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                        events.append(ActiveLoop("order_form"))

                    return events

                price = 0
                for order in ordered_list:
                    menu_price = TABLE.price[order['menu']]
                    if order['size'] == '미디움': menu_price += 500
                    elif order['size'] == '스몰': menu_price += 1000
                    
                    price += (menu_price * int(order['count']))
                
                dispatcher.utter_message(text=f"총 {price}원을 주문하셨습니다.")
                return []
        
        elif len(asks) == 1: # only one group
            ask = list(asks.values())[0]
            if 'menu' not in ask:
                if len(ask) == 1 and 'size' in ask:
                    if ask['size'] == '스몰': dispatcher.utter_message(text="스몰 작은 사이즈는 추가금액이 없어요")
                    elif ask['size'] == '미디움' : dispatcher.utter_message(text="중간 사이즈는 500원이 추가돼요")
                    elif ask['size'] == '라지' : dispatcher.utter_message(text="라지 사이즈는 1000원원이 추가돼요")

                    if form_flag:
                        events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                        events.append(ActiveLoop("order_form"))
                        
                    return events
                else:
                    dispatcher.utter_message(text="죄송합니다. 말씀을 이해하지 못했어요") 

                    if form_flag:
                        events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                        events.append(ActiveLoop("order_form"))
                    return events
            else:
                menu_price = TABLE.price[ask['menu']]
                size,cnt = None,None
                if 'size' in ask:
                    if ask['size']  == '스몰': size = 0
                    elif ask['size'] == '미디움': size = 500
                    elif ask['size'] == '라지': size = 1000
                if 'count' in ask: cnt = int(ask['count'])
                
                if size is not None and cnt is None:
                    dispatcher.utter_message(text=f"{ask['menu']} {ask['size']}사이즈는 {menu_price + size}원입니다.")
                elif size is None and cnt is not None:
                    dispatcher.utter_message(text=f"{ask['menu']} {ask['count']}잔은 {menu_price * cnt}원입니다.")
                elif size is not None and cnt is not None:
                    dispatcher.utter_message(text=f"{ask['menu']} {ask['size']}사이즈 {ask['count']}잔은 {(menu_price + size) * cnt}원입니다.") 
                elif size is None and cnt is None:
                    dispatcher.utter_message(text=f"{ask['menu']}은 {menu_price}원입니다.")
        else: # multiple group
            response = ''
            for grp,ask in asks.items():
                if 'menu' not in ask:
                    dispatcher.utter_message(text="죄송합니다. 말씀을 이해하지 못했어요") 

                    if form_flag:
                        events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                        events.append(ActiveLoop("order_form"))
                    return events
                
                menu_price = TABLE.price[ask['menu']]
                size,cnt = None,None
                if 'size' in ask:
                    if ask['size']  == '스몰': size = 0
                    elif ask['size'] == '미디움': size = 500
                    elif ask['size'] == '라지': size = 1000
                if 'count' in ask: cnt = int(ask['count'])
                if size is not None and cnt is None:
                    response += f"{ask['menu']} {ask['size']}사이즈는 {menu_price + size}원,"
                elif size is None and cnt is not None:
                    response += f"{ask['menu']} {ask['count']}잔은 {menu_price * int(ask['count'])}원,"
                elif size is not None and cnt is not None:
                    response += f"{ask['menu']} {ask['size']}사이즈 {ask['count']}잔은 {(menu_price + size) * cnt}원"
                elif size is None and cnt is None:
                    response += f"{ask['menu']}은 {menu_price}원,"
            
            response = response[:-1]
            response += "입니다"
    
            dispatcher.utter_message(text=response)

        if len(asks) >= 1:
            asked_queue = []
            for grp,ask in asks.items():
                if 'menu' in ask: asked_queue.append(ask)
            
            print(asked_queue)
            if len(asked_queue) != 0:
                events.append(SlotSet("asked_queue",asked_queue))

                if form_flag:
                    events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
                    events.append(ActiveLoop("order_form"))
                return events
        
        if form_flag:
            events += [SlotSet(key,val) for key,val in before[0].items()] # order_form을 처리 중이였던 상황
            events.append(ActiveLoop("order_form"))

        return events


# 그럼 그걸로 주세요, 그럼 그걸로 2잔 할게요,....그럼 망고주스는 하나,  # 그럼 두잔씩 주세요
class order_after_ask(Action):
    def name(self):
        return "action_order_after_ask" # 이미 메뉴는 검증되어 있음 (asked_queue에 들어가 있음)

    def run(self, dispatcher, tracker, domain):
        # latest_user_message = None
        # for event in reversed(tracker.events):
        #     if event.get('event') == 'user':
        #         latest_user_message = event.get('text')
        #         break

        # if latest_user_message is None:
        #     dispatcher.utter_message(text="죄송합니다. 잘 이해하지 못했어요. 다시 말씀해주세요")
        #     return [] 
        
        asked_queue = tracker.get_slot("asked_queue")

        if asked_queue is None or len(asked_queue) == 0:
            dispatcher.utter_message(response="utter_ask_menu")
            ordered_queue = tracker.get_slot("ordered_queue")
            return [Restarted(),SlotSet("ordered_queue",ordered_queue)]
        
        for i,order in enumerate(asked_queue):
            temp = drink_temp(order['menu'])
            if 'temp' not in order or order['temp'] is None: asked_queue[i]['temp'] = temp
                
        
        entities = tracker.latest_message['entities'] # 그럼 그걸로 주세요 -> 여러 개 질문 처리 가능  # ~잔씩 거리 가능해야함

        events = []
        events.append(SlotSet("asked_queue",None))
        if len(asked_queue) >= 1:
            if len(entities) == 0: # 그럼 그걸로 주세요 -> 이전에 물어본것 그대로 주문
                before = {key:None for key in ORDER_REQUIRED_ENTITY}
                order = asked_queue.pop(0)
                for key,val in order.items():
                    events.append(SlotSet(key,val))
                    before[key] = val
                
                events.append(SlotSet("before",[before]))

                if len(asked_queue) != 0:
                    events.append(SlotSet("order_queue",asked_queue))
                
            else:
                # entity -> asked_queue 업데이트!
                update = {}
                for entity in entities:
                    val = entity['value']
                    val = _valid(val,entity['entity'])
                    if val is None:
                        dispatcher.utter_message(text="죄송합니다. 잘 이해하지 못했어요. 다시 말씀해주세요")
                        return []  
                    update[entity['entity']] = val
                
                for i in range(len(asked_queue)):
                    for key,val in update.items():
                        asked_queue[i][key] = val

                order = asked_queue.pop(0)
                before = {key:None for key in ORDER_REQUIRED_ENTITY}
                for key,val in order.items():
                    events.append(SlotSet(key,val))
                    before[key] = val
                events.append(SlotSet("before",[before]))
                
                if len(asked_queue) != 0:
                    events.append(SlotSet("order_queue",asked_queue))

        else:
            dispatcher.utter_message(text="죄송합니다. 잘 이해하지 못했어요. 다시 말씀해주세요")
            
        return events

class q_menu(Action): #어떤 메뉴가 있는지 요청
    def name(self):
        return "action_q_menu"

    def run(self, dispatcher, tracker, domain):
        # 슬롯에서 데이터 추출
        category = tracker.get_slot('category')
        kr_category = {'커피' : 'coffee', '라떼' : "latte", '티' : 'tea', '차' : 'tea', '주스' : 'juice', '에이드' : 'ade', '스무디' : 'smoothie'}

        if category is None:
            dispatcher.utter_message(text="저희 매장은 커피,라떼,티,주스,에이드,스무디를 판매하고 있어요")
        else:
            category = category.replace("","")
            category = kr_category[category]
            
            if category not in TABLE.category_to_drink.keys(): dispatcher.utter_message(text="저희 매장은 커피,라떼,티,주스,에이드,스무디를 판매하고 있어요")
            else:
                drinks = random.sample(TABLE.category_to_drink[category],4)
                drink_text = ", ".join(drinks[:-1]) + "와 " + drinks[-1]
                message = f"저희 매장은 {drink_text}를 판매하고 있어요."
                dispatcher.utter_message(text=message)

        return [SlotSet('category',None)]

def drink_to_category(drink):
    for category,drink_list in TABLE.category_to_drink.items():
        if drink in drink_list: return category
    return None

def drink_temp(menu):
    menu_category = drink_to_category(menu)
    if menu == '핫초코': return '핫'
    if menu == '아아' : return '아이스'
    if menu == '아이스티' : return '아이스'
    if menu == '아샷추' : return '아이스'
    if menu == '딸기라떼': return '아이스'

    if menu_category in ['juice','ade','smoothie']:
        return '아이스'
    
    return None
    

def _valid(value,entity_type):
    entity_to = {
        'temp' : TABLE.temp_to_category,
        'count' : TABLE.count_to_int,
        'size' : TABLE.size_to_category
    }
    if entity_type == 'menu':
        menu_list = [drink for drinks in TABLE.category_to_drink.values() for drink in drinks]

        if isinstance(value,list):
            for i_value in value:
                _value = i_value.replace(" ","")
                if _value in menu_list: return _value
            return None
        else:
            _value = value.replace(" ","")
            if _value in menu_list : return _value
            else: return None

    if isinstance(value, list):
        for i_value in value:
            _value = i_value.replace(" ","")
            if _value in entity_to[entity_type].keys(): return str(entity_to[entity_type][_value])
        return None
    else:
        _value = value.replace(" ","") # 공백제거
        if _value in entity_to[entity_type].keys(): return str(entity_to[entity_type][_value])
        else: return None