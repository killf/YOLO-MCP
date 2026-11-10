import React, { memo, useContext } from 'react';
import { Form, Input, Select } from 'antd';
import styled from 'styled-components';
import { FlexLayout } from '@yolo-mcp/components-react';
import { useTranslation } from '@yolo-mcp/i18n';

import { MediaType } from '@/api/types';

import { ProjectCreationContext } from '../../projectCreation.context';

const Inner = styled(FlexLayout)`
  width: 740px;
  margin: auto;
`;

const InputInfoConfig = () => {
  const { basicFormInstance } = useContext(ProjectCreationContext);
  const { t } = useTranslation();

  return (
    <FlexLayout padding="1rem" flex="column">
      <Inner flex="column">
        <h2>{t('basicConfig')}</h2>
        <FlexLayout.Content>
          <Form form={basicFormInstance} labelCol={{ span: 3 }} wrapperCol={{ span: 21 }}>
            <Form.Item
              label={t('projectName')}
              name="name"
              required
              rules={[{ required: true, message: t('projectNameRequired') }]}
            >
              <Input placeholder={t('projectName50CharactersPlease')} maxLength={50} />
            </Form.Item>
            <Form.Item
              label={t('mediaType')}
              name="media_type"
              rules={[{ required: true, message: t('mediaTypeRequired') }]}
            >
              <Select
                placeholder={t('selectMediaTypePlease')}
                options={[
                  {
                    label: t('image'),
                    value: MediaType.IMAGE,
                  },
                ]}
              />
            </Form.Item>
            <Form.Item label={t('projectDescription')} name="description">
              <Input.TextArea placeholder={t('projectDescription500CharactersPlease')} maxLength={500} rows={6} />
            </Form.Item>
            <Form.Item label={t('projectTip')} name="tips">
              <Input.TextArea placeholder={t('projectTipPlaceholder')} maxLength={1000} rows={6} />
            </Form.Item>
          </Form>
        </FlexLayout.Content>
      </Inner>
    </FlexLayout>
  );
};
export default memo(InputInfoConfig);
