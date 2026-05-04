import request from './http'

export function pageFeedback(params) {
  return request({
    url: '/feedback/page',
    method: 'get',
    params
  })
}

export function getFeedback(id) {
  return request({
    url: `/feedback/${id}`,
    method: 'get'
  })
}

export function createFeedback(data) {
  return request({
    url: '/feedback',
    method: 'post',
    data
  })
}

export function replyFeedback(id, data) {
  return request({
    url: `/feedback/${id}/reply`,
    method: 'post',
    data
  })
}
