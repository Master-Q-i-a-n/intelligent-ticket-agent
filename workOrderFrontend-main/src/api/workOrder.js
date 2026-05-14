import request from './http'

export function pageWorkOrders(params) {
  return request({
    url: '/work-order/page',
    method: 'get',
    params
  })
}

export function getWorkOrderSummary(params) {
  return request({
    url: '/work-order/summary',
    method: 'get',
    params
  })
}

export function updateWorkOrderStatus(id, data) {
  return request({
    url: `/work-order/${id}/status`,
    method: 'post',
    data
  })
}

export function getWorkOrderDetail(id) {
  return request({
    url: `/work-order/${id}`,
    method: 'get'
  })
}

export function replyWorkOrder(id, data) {
  return request({
    url: `/work-order/${id}/reply`,
    method: 'post',
    data
  })
}

export function getSuggestion(id){
  return request({
    url: `/work-order/${id}/suggest`,
    method: 'get'
  })
}
