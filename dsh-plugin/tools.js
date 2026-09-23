import { createHash, randomUUID } from 'node:crypto';
import { defineTool } from '@deepseek-ai/dsh-tools';
import z from '@deepseek-ai/schemastery';
import { runPython } from './runner.js';

export const inject = ['tools', 'settings', 'credentials'];
export const Config = z.object({
  pythonPath: z.string().required(),
  projectDir: z.string().required(),
});

const output = {
  schema: { type: 'json' },
  render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
};
const contact = {
  type: 'object', additionalProperties: false, required: true,
  properties: {
    name: { type: 'string', required: true, description: '姓名' },
    mobile: { type: 'string', required: true, description: '手机号' },
    province: { type: 'string', required: true, description: '省/直辖市' },
    city: { type: 'string', required: true, description: '城市' },
    county: { type: 'string', description: '区县' },
    address: { type: 'string', required: true, description: '详细地址' },
  },
};

export function apply(ctx, config) {
  async function invoke(operation, payload, exec) {
    const settings = ctx.settings.describe().find(row => row.ns === 'sf-express-settings')?.value;
    if (!settings || !['sandbox', 'production'].includes(settings.environment)) {
      throw new Error('请先在设置 → 顺丰速运中选择环境并配置凭据');
    }
    const environment = settings.environment;
    const prefix = environment === 'production' ? 'SF_DSH_PRODUCTION' : 'SF_DSH_SANDBOX';
    const saved = await ctx.credentials.resolve(`${prefix}_CREDENTIALS`);
    let credentials;
    try { credentials = JSON.parse(saved?.value || 'null'); } catch { credentials = null; }
    if (!credentials?.partner_id || !credentials?.checkword) throw new Error(`请先在设置 → 顺丰速运中配置${environment === 'production' ? '生产' : '沙盒'}凭据`);
    const request = {
      operation, payload, environment, partner_id: credentials.partner_id, checkword: credentials.checkword,
      sign_mode: environment === 'production' ? settings.productionSignMode : settings.sandboxSignMode,
    };
    try {
      return { ...await runPython(config, request, exec.signal), environment };
    } catch (error) {
      if (operation === 'track') throw error;
      return { status: 'outcome_unknown', environment, order_id: payload.order_id ?? null,
        message: '调用未能返回结果，请核实订单状态，勿自动重复操作。' };
    }
  }

  ctx.tools.register(defineTool({
    name: 'sf_create_order',
    description: '向配置的顺丰环境下单。生产环境会创建真实订单。先展示寄收件信息、托寄物、付款和揽收选项并取得本次确认。客户订单号可省略自动生成；结果不确定时禁止盲目重下。',
    parameters: {
      confirmed: { type: 'boolean', required: true, description: '仅在用户已确认本次订单后填 true' },
      order: { type: 'object', additionalProperties: false, required: true, properties: {
        order_id: { type: 'string', description: '通常省略自动生成；核实/重试已有订单时保持原值' },
        sender: contact, recipient: contact,
        cargo: { type: 'array', required: true, items: { type: 'object', additionalProperties: false, properties: {
          name: { type: 'string', required: true }, count: { type: 'integer' }, weight_kg: { type: 'number' },
        } } },
        parcel_qty: { type: 'integer' }, total_weight_kg: { type: 'number' },
        pay_method: { type: 'integer', enum: [1, 2, 3], description: '1寄方付，2收方付，3第三方付' },
        express_type_id: { type: 'integer' }, monthly_card: { type: 'string' },
        pickup_time: { type: 'string' }, request_pickup: { type: 'boolean' }, remark: { type: 'string' },
      } },
    }, output,
    execute(args, exec) {
      if (args.confirmed !== true) throw new Error('请先获得用户对本次下单的明确确认');
      const identity = exec.agent ? `${exec.agent.id}:${exec.callId}` : randomUUID();
      const order_id = args.order.order_id || `DSH-${createHash('sha256').update(identity).digest('hex').slice(0, 32)}`;
      return invoke('create', { ...args.order, order_id }, exec);
    },
  }));
  ctx.tools.register(defineTool({
    name: 'sf_track_shipment',
    description: '按顺丰运单号或客户订单号查询物流轨迹。通过本服务下单的运单号可在24小时内返回对应客户订单号。',
    parameters: {
      tracking_type: { type: 'string', required: true, enum: ['waybill', 'order'] },
      tracking_number: { type: 'string', required: true },
    }, output,
    execute: (args, exec) => invoke('track', args, exec),
  }));
  ctx.tools.register(defineTool({
    name: 'sf_cancel_order',
    description: '取消发货前的顺丰订单。先核对目标并取得本次取消的明确确认。提供客户订单号，或本服务24小时内保存的运单号，两者只填一个。结果不确定时不要自动重试。',
    parameters: {
      order_id: { type: 'string', description: '原客户订单号' },
      waybill_number: { type: 'string', description: '本机24小时内保存的运单号' },
      confirmed: { type: 'boolean', required: true, description: '仅在用户明确确认本次取消后填 true' },
    }, output,
    execute(args, exec) {
      if (args.confirmed !== true) throw new Error('请先获得用户对本次取消的明确确认');
      if (Boolean(args.order_id) === Boolean(args.waybill_number)) throw new Error('客户订单号和运单号必须且只能填写一个');
      return invoke('cancel', { ...(args.order_id ? { order_id: args.order_id } : { waybill_number: args.waybill_number }) }, exec);
    },
  }));
}
